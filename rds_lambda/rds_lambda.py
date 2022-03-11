import logging
import json
import os
import pymysql
import boto3
from botocore.exceptions import ClientError
import base64

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

_session = None

_db_conn = None

"""
create table if not exists Tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL
)

insert into Tasks (title)  values("task 1")
insert into Tasks (title) values("task 2")

"""

def _init(profile_name=None, region='us-east-1'):
    global _session

    if _session is None:
        if profile_name is None:
            _session = boto3.Session()
        else:
            _session = boto3.Session(profile_name=profile_name, region_name=region)

def _init_db_conn(rds_host, db_username, db_password, db_name):
    global _db_conn
    try:
        if _db_conn is None or not _db_conn.open:
            _db_conn = pymysql.connect(
                host=rds_host,
                user=db_username,
                password=db_password,
                db=db_name,
                connect_timeout=5
            )
    except Exception as exc:
        logger.error(exc)
        raise exc


def _get_secret(secret_name, region='us-east-1'):

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region
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

def _get_tasks():
    rows = []
    with _db_conn.cursor() as cur:
        cur.execute("select * from Tasks")
        for row in cur:
            logger.debug(row)
            rows.append(row)

    return rows

def lambda_handler(event, context):
    global _db_conn
    logger.debug("RDS Lambda Called")
    _init()

    rds_host = os.getenv('RDS_HOST', None)
    db_name = os.getenv('RDS_DB_NAME', None)
    secret_name = os.getenv('SECRET_NAME', None)

    try:
        if _db_conn is None:
            db_secret = _get_secret(secret_name)
            db_secret = json.loads(db_secret)
            db_username = db_secret['username']
            db_password = db_secret['password']
            logger.debug(f"DB Username: {db_username}")

            _init_db_conn(rds_host, db_username, db_password, db_name)

        tasks = _get_tasks()
    except Exception as exc:
        logger.error(f"Exception: {exc}")
        tasks = []
    finally:
        if _db_conn is not None and _db_conn.open:
            _db_conn.close()
            _db_conn = None

    responseBody = {
        "tasks": json.dumps(tasks)
    }
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        },
        "body": json.dumps(responseBody)
    }

