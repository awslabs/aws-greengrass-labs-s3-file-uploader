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





import sys
import time
import asyncio
import logging
from urllib.parse import urlparse
from src.DirectoryUploader import DirectoryUploader

# This example scans a folder for a file pattern and upload the files that match to S3
# The program monitor the completion of the S3 operation and upon succefull 


async def main(logger:logging.Logger, pathname,bucket_name,interval):

    logger.info("==== main ====")
    
    while True:
        du = None
        try:
            du = DirectoryUploader(pathname=pathname,bucket_name=bucket_name,interval=interval,logger=logger)
            await du.Run()
        except Exception:
            logger.exception("Exception while running")
        finally:
            if du is not None:
                du.Close()
        #something very wrong happened. Let's pause for 1 minute and start again
        time.sleep(60)



# Start up this sample code

if __name__ == "__main__":
    #args :  pathname, bucket_name, interval, log_level
    if len(sys.argv) == 5:
        #Todo: validate arguments.
        pathname = sys.argv[1]
        bucket_name = sys.argv[2]
        interval = sys.argv[3]
        log_level = sys.argv[4]

        logging.basicConfig(level=log_level)
        logger=logging.getLogger()

        logger.info(f'File uploader started with; pathname={pathname}, bucket_name={bucket_name}, interval={interval}')
        asyncio.run(main(logger,pathname,bucket_name,int(interval)))
    else:
        logging.basicConfig(level=logging.INFO)
        logger=logging.getLogger()
        logger.error(f'3 argument required, only {len(sys.argv)} provided.')


