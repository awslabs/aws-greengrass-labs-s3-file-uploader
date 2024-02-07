#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  
#  Licensed under the Apache License, Version 2.0 (the "License").
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  
#      http://www.apache.org/licenses/LICENSE-2.0
#  
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import asyncio
import glob
import os
import ntpath
from urllib.parse import urlparse
import logging

from datetime import datetime

from stream_manager import (
    ExportDefinition,
    MessageStreamDefinition,
    ReadMessagesOptions,
    ResourceNotFoundException,
    S3ExportTaskDefinition,
    S3ExportTaskExecutorConfig,
    Status,
    StatusConfig,
    StatusLevel,
    StatusMessage,
    StrategyOnFull,
    StreamManagerClient,
    StreamManagerException,
    ValidationException,
    NotEnoughMessagesException
)
from stream_manager.util import Util


class DirectoryUploader:
    """ DirectoryUploader monitors a folder for new files and upload those new files to S2 via stream manager"""

    __stream_name = "DirectoryUploader"
    __status_stream_name = "DirectoryUploaderStatus"
    
    def __init__(self, pathname, bucket_name, bucket_path, interval, logger:logging.Logger ,client:StreamManagerClient=None):
        self.__pathname = pathname
        self.__bucket_name = bucket_name
        self.__bucket_path = bucket_path.removeprefix("/").removesuffix("/")
        self.__stream_name = bucket_name + "Stream"
        self.__status_stream_name = self.__stream_name + "Status"
        self.__client = client
        if(self.__client == None):
            self.__client = StreamManagerClient() 
        self.__logger = logger
        self.__status_interval = max(interval,1)
        self.__filesProcessed = set()
        self.__interval=interval

        # Try deleting the stream and the status stream (if they exist) so that we have a fresh start
        # The impact of deleting the streams on startup is that:
        #   - Files might have been queued and their transfer will be cancelled. This is not a problem, the 
        #     files will be queued again.
        #   - Acknoledgment of file transfert will be missed. The file in question will be transferred again.

        try:
            self.__client.delete_message_stream(stream_name=self.__status_stream_name)
        except ResourceNotFoundException:
            pass

        # Try deleting the stream (if it exists) so that we have a fresh start
        try:
            self.__client.delete_message_stream(stream_name=self.__stream_name)
        except ResourceNotFoundException:
            pass

        exports = ExportDefinition(
            s3_task_executor=[
                S3ExportTaskExecutorConfig(
                    identifier="S3TaskExecutor" + self.__stream_name,  # Required
                    # Optional. Add an export status stream to add statuses for all S3 upload tasks.
                    status_config=StatusConfig(
                        status_level=StatusLevel.INFO,  # Default is INFO level statuses.
                        # Status Stream should be created before specifying in S3 Export Config.
                        status_stream_name=self.__status_stream_name,
                    ),
                )
            ]
        )

        # Create the Status Stream.
        self.__client.create_message_stream(
            MessageStreamDefinition(name=self.__status_stream_name,
                                    strategy_on_full=StrategyOnFull.OverwriteOldestData)
        )

        # Create the message stream with the S3 Export definition.
        self.__client.create_message_stream(
            MessageStreamDefinition(name=self.__stream_name,
                                    strategy_on_full=StrategyOnFull.OverwriteOldestData,
                                    export_definition=exports
            )
        )

    async def __scan(self, under_test=False):
        self.__logger.info("==== __scan  start ====")
        keep_looping = True
        while keep_looping:
            try:
                base_dir = os.path.dirname(self.__pathname)
                if ntpath.isdir(base_dir) and os.access(base_dir, os.R_OK|os.W_OK|os.X_OK):
                    self.__logger.info(f"Scanning folder {self.__pathname} for change ====")
                    files = glob.glob(self.__pathname)
                    files.sort(key=os.path.getmtime)
                    if(len(files) > 0):
                        #remove most recent file as it is considerred the active file
                        self.__logger.info(f'The current active file is : {files.pop()}')
                    fileset = set(files) - self.__filesProcessed
                    
                    if(len(fileset) == 0):
                        self.__logger.info('No new files to transfer')
                    
                    for file in fileset:

                        # Append a S3 Task definition and print the sequence number
                        head, tail = ntpath.split(file)
                        
                        # Create folder structure in the cloud
                        key = self.__bucket_path+"/"+tail
                        
                        # Print for logging
                        self.__logger.debug("TAIL VALUE: " + tail)
                        self.__logger.debug("FINAL KEY VALUE: " + key)
                        
                        s3_export_task_definition = S3ExportTaskDefinition(input_url="file://"+file,
                                                                        bucket=self.__bucket_name,
                                                                        key=key)
                        payload = None
                        try:
                            payload = Util.validate_and_serialize_to_json_bytes(s3_export_task_definition)
                        except ValidationException:
                            # if validation failed, file will not be sent to S3 and we will not retry unitil
                            # component is re-started
                            self.__logger.warning(f'Validation failed for file: {file},' +
                                                f' buckt: {self.__bucket_name}, key: {tail}. File not sent to S3')

                        if(payload != None):
                            self.__logger.info(
                                "Successfully appended S3 Task Definition to stream with sequence number %d",
                                self.__client.append_message(self.__stream_name, payload),
                            )
                    # we could compute the new self.__filesProcessed as self.__filesProcessed.union(fileset)
                    # but that would mean an ever growing set
                    # instead we compute it as set(files) which is the list of files at the begining of this iteration
                    # minus the current active file
                    self.__filesProcessed =  set(files)
                    await asyncio.sleep(self.__interval)
                else:
                    self.__logger.error(f"The path {base_dir} is not a directory, does not exists or greengrass user doesn't have sufficient (rwx) access.")
                    #let wait 1 minute before retrying
                    if not under_test:
                        await asyncio.sleep(60)
            except Exception:
                self.__logger.exception("Exception while scanning folder")
            keep_looping= not under_test


    async def __processStatus(self,under_test=False):
        # Read the statuses from the export status stream
        self.__logger.info("==== __processStatus start ====")
        next_seq = 0
        keep_looping = True
        while keep_looping:
            try:
                self.__logger.info("Reading messages from status stream")
                messages_list = self.__client.read_messages( self.__status_stream_name,
                                                             ReadMessagesOptions(desired_start_sequence_number=next_seq,
                                                                                min_message_count=1,
                                                                                max_message_count=5,
                                                                                read_timeout_millis=1000))
                for message in messages_list:
                    # Deserialize the status message first.
                    status_message = Util.deserialize_json_bytes_to_obj(message.payload, StatusMessage)
                    file_url = status_message.status_context.s3_export_task_definition.input_url

                    # Check the status of the status message. If the status is "Success",
                    # the file was successfully uploaded to S3.
                    # If the status was either "Failure" or "Cancelled", the server was unable to upload
                    # the file to S3. We will print the message for why the upload to S3 failed from the
                    # status message. If the status was "InProgress", the status indicates that the server
                    # has started uploading the S3 task.
                    if status_message.status == Status.Success:
                        self.__logger.info(f'Successfully uploaded file at path {file_url} to S3.')
                        p = urlparse(file_url)
                        final_path = os.path.abspath(os.path.join(p.netloc, p.path))
                        # on linux removing a file that is in use will sucseed. On windows it will generate
                        # an exception
                        os.remove(final_path)
                    elif status_message.status == Status.InProgress:
                        self.__logger.info('File upload is in Progress.')
                    elif status_message.status == Status.Failure or status_message.status == Status.Canceled:
                        self.__logger.error(
                            f'Unable to upload file at path {file_url} to S3. Message: {status_message.message}')
                        
                        # remove the file from the list of files already processed and let it be tried again.
                        self.__filesProcessed.remove(file_url.partition("file://")[2])

                    next_seq = message.sequence_number + 1
            except NotEnoughMessagesException:
                # ingore this exception, it doesn't mean something went wrong.
                pass
            except Exception:
                self.__logger.exception("Exception while processing status")
            self.__logger.info(f"Sleeping for {self.__status_interval} seconds")
            await asyncio.sleep(self.__status_interval)
            keep_looping= not under_test

    async def Run(self):
        tasks = [asyncio.create_task(self.__scan()),asyncio.create_task(self.__processStatus())]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    def Close(self):
        self.__client.close()
