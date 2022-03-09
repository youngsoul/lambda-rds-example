import aws_cdk as core
import aws_cdk.assertions as assertions

from lambda_rds_example.lambda_rds_example_stack import LambdaRdsExampleStack

# example tests. To run these tests, uncomment this file along with the example
# resource in lambda_rds_example/lambda_rds_example_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = LambdaRdsExampleStack(app, "lambda-rds-example")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
