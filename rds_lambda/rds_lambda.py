import logging
import json
import os
import pymysql
import boto3
from botocore.exceptions import ClientError
import base64

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

session = None

def _init(profile_name=None, region='us-east-1'):
    global session

    if session is None:
        if profile_name is None:
            session = boto3.Session()
        else:
            session = boto3.Session(profile_name=profile_name, region_name=region)


def get_secret(secret_name):

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager'
    )

    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS key.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])

    return secret



def lambda_handler(event, context):
    logger.debug("RDS Lambda Called")
    _init()

    rds_host = os.getenv('RDS_HOST', None)
    rds_username = os.getenv('RDS_USERNAME', None)
    db_name = os.getenv('RDS_DB_NAME', None)
    secret_name = os.getenv('SECRET_NAME', None)

    responseBody = {
        "msg": "this space for rent"
    }
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        },
        "body": json.dumps(responseBody)
    }


if __name__ == '__main__':
    _init(profile_name='pryan')
    print(get_secret("mysupersecretname"))