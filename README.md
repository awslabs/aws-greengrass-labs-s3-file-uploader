## aws-greengrass-labs-s3-file-uploader

This component monitors a directory for new files, upload them to S3 and delete them upon successful upload.
For the upload to S3, aws-greengrass-labs-s3-file-uploader uses greengrass stream manager.
Asyncio is used to monitor concurrently the directory and the stream manager status stream.

The logic to scan the folder is to list all of the files that match a pattern, sort them by last modified date, remove the most recent file and send the remaining files to stream manager for upload.

The most recent file is considered the active file and the producer might still be writing to it.
The caveat of this approach is that if there is only one file in the folder it will not be sent to S3.
The delivery guarantee is at least once, meaning that in case of transmission errors and retry, the same file might be uploaded multiple time.
The user under which this component runs need to have rwx permission on the directory where the files are located.
Write and execute are required so that files can be deleted after transfer.

## Downloading this component
You can either clone this repo with git, or download this component as a zip file.  

NOTE THAT THE FOLDER IN WHICH YOU CLONE OR UNZIP THIS COMPONENT NEEDS TO BE CALLED ```aws-greengrass-labs-s3-file-uploader``` FOR GDK TO WORK PROPERLY

## Installing dependencies
It is recommended to create a virtual environment to install dependencies. To do so, run the following commands in the root folder of this repo:  
```bash
 python3 -m venv .venv
 source ./.venv/bin/activate
```

This component can be built with [GDK](https://docs.aws.amazon.com/greengrass/v2/developerguide/gdk-cli-configuration-file.html), and uses pytest for unit testing.  
To install those dev dependencies as well as the runtime dependencies so that tools like Pylance work properly, run the following command in the virtual environment you just created:

```bash
pip3 install -r requirements_dev.txt
```
## Build

Before building the component, you will need to update the gdk-config.json file, replacing the bucket and region placeholder.
```
      "publish": {
        "bucket": "<PLACEHOLDER BUCKET HERE>",
        "region": "<PLACEHOLDER REGION>"
      }
```
The bucket is where the component artefact will be uploaded when you publish the component, and region is the region where the greengrass component will be created.

Once this is done, you can build the component with the following command:
```
gdk component build
```
## Publish
Before you can deploy aws-greengrass-labs-s3-file-Uploader to your device, you first need to publish your component.
This can be done with the following command:
```
gdk component publish
```

You should now be able to see the aws-greengrass-labs-s3-file-Uploader component in the *Greengrass->component* section of the AWS console.
It can now be included in a Greengrass deployment and pushed to your device.

Note: for the component to run successfully you need to update the default configuration when you deploy the component, see next section.

## Configuration
This component provides the following configuration parameters when it is deployed:

    PathName: "/local/path/to/monitor/*.ext"
    BucketName: "bucket-name-where-to-upload-files"
    ObjectKeyPrefix: "a prefix to add to the object name in S3"
    Interval: <time in second between the scans>

PathName is a path with pattern expansion as described [here](https://docs.python.org/3/library/glob.html). Some valid examples are:
```
/user/ggc_user/upload/*.cvs
/user/ggc_user/logs/*.log

``` 

ObjectKeyPrefix allows you to put the files in a subfolder in the S3 bucket. The object name will be : s3://BucketName/ObjectKeyPrefix/orginalfilename

You need to make sure that the role   
GreengrassV2TokenExchangeRole has access to the bucket listed in the configuration.

You need to make sure that the local ggc_user has access to PathName.

## Testing
Deploy the component with the following configuration:
```
PathName: "/home/gcc_user/upload/*.txt"
BucketName: <put-you-bucket-name-here>
Interval: 10
```
Log into the component and create a text file in the /home/gcc_user/upload folder: 
```
echo test1.txt > /home/gcc_user/upload
```
Create another test file:
```
echo test2.txt > /home/gcc_user/upload
```

Check that test1.txt has been uploaded to S3 bucket, you mayhave to wait 10s.

## Local log file
This component uses the following local log file:
```
/greengrass/v2/logs/aws.greengrass.labs.s3.file.Uploader.log
```

## Running unit tests
You can run the unit tests by running the following command from the root folder of the repo:  
```bash
pytest tests
```
## License

This library is licensed under the Apache 2.0 License.
