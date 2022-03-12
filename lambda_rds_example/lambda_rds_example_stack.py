import json

from aws_cdk import (
    # Duration,
    Stack,
    aws_ec2 as ec2,
    aws_secretsmanager as secrets,
    aws_ssm as ssm,
    aws_rds as rds,
    RemovalPolicy,
    CfnOutput,
    aws_lambda_python_alpha as lambda_alpha_,
    aws_lambda as _lambda,
    Duration,
    aws_apigatewayv2_integrations_alpha as integrations,
    aws_apigatewayv2_alpha as api_gw,

)
from constructs import Construct

resource_prefix = 'lambda-rds'
mysql_port = 3306
db_username = "retireddev"
db_name = "testdb"


class LambdaRdsExampleStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # by default this will:
        # * create a vpc with 2 AZs
        # * default ip addresses in 10.x.x.x
        # * create a private and public subnet in each AZ
        # * create NATGateway in each of the public subnets
        # * create default route table for each of the subnets
        # ** public subnet route tables has route to igw
        # ** private subnet route tables has route to nat
        # * default security group is all traffic in/out
        # vpc = ec2.Vpc(self, f'{resource_prefix}-Vpc', max_azs=2)

        # the below configuration will create a public and private subnet
        # and create a nat_gateway to route traffic from private to public igw
        # I believe the only way around that is to create subnet_configurations=[]
        #   with just a public.
        vpc = ec2.Vpc(self, f'{resource_prefix}-Vpc',
                      cidr='10.40.0.0/16',
                      nat_gateways=1,
                      max_azs=2,
                      enable_dns_hostnames=True,
                      enable_dns_support=True,
                      subnet_configuration=[
                          ec2.SubnetConfiguration(
                              name=f"{resource_prefix}-Public-subnet",
                              subnet_type=ec2.SubnetType.PUBLIC,
                              cidr_mask=24
                          ),
                          ec2.SubnetConfiguration(
                              name=f"{resource_prefix}-Private-subnet",
                              subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT,
                              cidr_mask=24
                          ),
                          ec2.SubnetConfiguration(
                              name=f"{resource_prefix}-Isolated-subnet",
                              subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                              cidr_mask=24
                          )
                      ],

                      )

        # We need this security group to add an ingress rule and allow our lambda to query the proxy
        lambda_to_proxy_sg = ec2.SecurityGroup(self, id=f'{resource_prefix}-l2proxy-sg',
                                               vpc=vpc,
                                               allow_all_outbound=True,  # default is True
                                               description="Lambda to RDS Proxy Connection"
                                               )
        bastion_sg = ec2.SecurityGroup(self, id='bastionsg',
                                       security_group_name=f'{resource_prefix}-cdk-bastion-sg',
                                       vpc=vpc,
                                       description=f'{resource_prefix} SG for Bastion',
                                       allow_all_outbound=True)
        # add SSH inbound rule
        # self.bastion_sg.add_ingress_rule(ec2.Peer.any_ipv4(), # any machine is allowed to ssh
        #                                  ec2.Port.tcp(22),
        #                                 description='SSH Access')
        bastion_sg.add_ingress_rule(ec2.Peer.ipv4('xxx.xxx.xxx.xxx/32'),  # only my machine
                                    ec2.Port.tcp(22),
                                    description='SSH Access')

        # We need this security group to allow our proxy to query our MySQL Instance
        db_connection_sg = ec2.SecurityGroup(self, id=f'{resource_prefix}-proxy2db-sg',
                                             description='Proxy to DB Connection',
                                             vpc=vpc,
                                             allow_all_outbound=False
                                             )
        db_connection_sg.add_ingress_rule(peer=db_connection_sg,
                                          connection=ec2.Port.tcp(3306),
                                          description='allow db connection')
        db_connection_sg.add_ingress_rule(peer=lambda_to_proxy_sg,
                                          connection=ec2.Port.tcp(3306),
                                          description='allow lambda connection')
        db_connection_sg.add_ingress_rule(peer=bastion_sg,
                                          connection=ec2.Port.tcp(3306),
                                          description='allow ec2 connection')

        # -------------------------------------------------------------------
        #           Secrets Manager
        # -------------------------------------------------------------------
        secrets_template = json.dumps({
            "username": f'{db_username}'
        })
        db_credentials_secret = secrets.Secret(self, id=f'{resource_prefix}-DBCredentialsSecret',
                                               secret_name=construct_id + '-rds-credentials',
                                               generate_secret_string=secrets.SecretStringGenerator(
                                                   secret_string_template=secrets_template,
                                                   exclude_punctuation=True,
                                                   include_space=False,
                                                   generate_string_key="password"
                                               ))

        # ssm.StringParameter(self, 'DBCredentialsArn',
        #                     parameter_name='rds-credentials-arn',
        #                     string_value=db_credentials_secret.secret_arn)

        # -------------------------------------------------------------------
        #           RDS
        # -------------------------------------------------------------------
        # NOTE:  RDS requires a VPC with at least 2 AZs

        """
        Resource handler returned message: "RDS is not authorized to assume service-linked 
        role arn:aws:iam::488518594239:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS 
        (Service: AWSSecurityTokenService; Status Code: 403; Error Code: AccessDenied; 
        Request ID: a71804e3-78c7-4ccf-ba2a-539959e652d1; Proxy: null). 
        Check your RDS service-linked role and try again. 
        (Service: AmazonRDS; Status Code: 400; Error Code: InvalidParameterValue; 
        Request ID: 23bd641f-f99b-48c7-a218-9852bde37d04; Proxy: null)" 
        (RequestToken: 7906c334-d550-a58c-db27-ec25b0386070, HandlerErrorCode: GeneralServiceException)
        
        ANS: https://aalvarez.me/posts/troubleshooting-strange-aws-issues/
        ANS: https://serverfault.com/questions/920834/cant-add-rds-database-to-elastic-beanstalk-environment
         
         Add the following policy to person running the command.  After I did this, the AWSServiceRoleForRDS showed up as a Role.
         
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "iam:GetServiceLinkedRoleDeletionStatus",
                "iam:CreateServiceLinkedRole",
                "iam:UpdateRoleDescription",
                "iam:DeleteServiceLinkedRole"
            ],
            "Resource": "arn:aws:iam::*:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS",
            "Condition": {
                "StringLike": {
                    "iam:AWSServiceName": "rds.amazonaws.com"
                }
            }
        }
    ]
}
         
        """
        # MySQL DB Instance (delete protection turned off because pattern is for learning.)
        # re-enable delete protection for a real implementation
        rds_instance = rds.DatabaseInstance(self,
                                            id=f'{resource_prefix}-DBInstance',
                                            engine=rds.DatabaseInstanceEngine.mysql(
                                                version=rds.MysqlEngineVersion.VER_8_0_16),
                                            credentials=rds.Credentials.from_secret(db_credentials_secret),
                                            instance_type=
                                            ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.MICRO),
                                            vpc=vpc,
                                            vpc_subnets=ec2.SubnetSelection(
                                                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                                            ),
                                            database_name=db_name,
                                            port=mysql_port,
                                            removal_policy=RemovalPolicy.DESTROY,
                                            deletion_protection=False,
                                            security_groups=[db_connection_sg],
                                            publicly_accessible=False,
                                            multi_az=False  # default value: False
                                            )

        # Create an RDS proxy
        proxy = rds_instance.add_proxy(construct_id + '-proxy',
                                       secrets=[db_credentials_secret],
                                       debug_logging=True,
                                       vpc=vpc,
                                       require_tls=False,
                                       security_groups=[db_connection_sg])

        # Workaround for bug where TargetGroupName is not set but required
        target_group = proxy.node.find_child('ProxyTargetGroup')
        target_group.add_property_override('TargetGroupName', 'default')

        # -------------------------------------------------------------------
        #           EC2
        # -------------------------------------------------------------------

        bastion_host = ec2.Instance(self, id=f'{resource_prefix}-bastion-host',
                                    instance_type=ec2.InstanceType(instance_type_identifier='t2.micro'),
                                    machine_image=ec2.AmazonLinuxImage(
                                        edition=ec2.AmazonLinuxEdition.STANDARD,
                                        generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
                                        virtualization=ec2.AmazonLinuxVirt.HVM,
                                        storage=ec2.AmazonLinuxStorage.GENERAL_PURPOSE
                                    ),
                                    vpc=vpc,
                                    key_name='pryan-aws',  # must create the key name manually first
                                    # this is the pem private/public key
                                    vpc_subnets=ec2.SubnetSelection(
                                        # this will create the ec2 instance in one of the PUBLIC subnets of the VPC that we just defined above
                                        subnet_type=ec2.SubnetType.PUBLIC
                                    ),
                                    security_group=bastion_sg
                                    )

        # -------------------------------------------------------------------
        #           Lambda
        # -------------------------------------------------------------------
        # The code that defines your stack goes here
        lb1 = lambda_alpha_.PythonFunction(self, f"{resource_prefix}-function",
                                           entry="./rds_lambda",
                                           index="rds_lambda.py",
                                           handler="lambda_handler",
                                           runtime=_lambda.Runtime.PYTHON_3_9,
                                           vpc=vpc,
                                           vpc_subnets=ec2.SubnetSelection(
                                               # this will create the ec2 instance in one of the PUBLIC subnets of the VPC that we just defined above
                                               subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT
                                           ),
                                           security_groups=[
                                               lambda_to_proxy_sg
                                           ],
                                           timeout=Duration.seconds(30),
                                           environment={
                                               "RDS_HOST": proxy.endpoint,
                                               "RDS_DB_NAME": db_name,
                                               "SECRET_NAME": construct_id + '-rds-credentials',

                                           }

        )

        # give the lambda read access to the secrets manager
        db_credentials_secret.grant_read(lb1)

        # defines an API Gateway Http API resource backed by our "efs_lambda" function.
        # -------------------------------------------------------------------
        #           Http Api
        # -------------------------------------------------------------------
        api = api_gw.HttpApi(self, f'{resource_prefix}-Test API Lambda',
                             default_integration=integrations.HttpLambdaIntegration(id="lb1-lambda-proxy",
                                                                                    handler=lb1))


        CfnOutput(
            scope=self,
            id="PublicIp",
            value= bastion_host.instance_public_ip,
            description="public ip of bastion host",
            export_name="ec2-public-ip")

        CfnOutput(self, 'HTTP API Url', value=api.url)

        CfnOutput(
            scope=self,
            id="dbEndpoint",
            value= rds_instance.instance_endpoint.hostname,
            description="db host")

        CfnOutput(
            scope=self,
            id="proxyDbEndpoint",
            value=proxy.endpoint
        )