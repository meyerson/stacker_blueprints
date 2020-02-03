from troposphere import Ref, Template, Output
from troposphere.apigateway import RestApi, Method
from troposphere.apigateway import Resource, MethodResponse
from troposphere.apigateway import Integration, IntegrationResponse
from troposphere.apigateway import Deployment, Stage, ApiStage
from troposphere.apigateway import UsagePlan, QuotaSettings, ThrottleSettings
from troposphere.apigateway import ApiKey, StageKey, UsagePlanKey
from troposphere.iam import Role, Policy
from troposphere.awslambda import Function, Code
from troposphere import GetAtt, Join

from stacker.blueprints.base import Blueprint
from stacker.blueprints.variables.types import TroposphereType


# adapted from https://github.com/cloudtools/troposphere/blob/master/examples/ApiGateway.py

class RestGateway(Blueprint):

    # where we set variable defaults - overriden the the yml

    VARIABLES = {
                    'ApiName':
                        {"type": str, "description": "API gateaway name"},
                    'FunctionName':
                        {"type":str, "default":"FunctionName"},
                    'runtime':
                        {"type":str, "default":"python3.7"},
                    'handler':
                        {"type":str, "default": "index.handler"},
                    'pathpart':
                        {"type":str, "default": "stuff"}
                    # 'paths':
                    #     {"type": list, "description": ""}
                    }

    def create_rest_gateway(self):
        t = self.template
        variables = self.get_variables()
        print("restapi variables: {}".format(self.get_variables()))
        # Create the Api Gateway

        rest_api = t.add_resource(RestApi(
            "ApiGateway",
            Name=variables['ApiName']
        ))
        
        t.add_output(Output("RestGatewayId", Value=Ref('ApiGateway')))

    def create_template(self):
        self.create_rest_gateway()
        self.create_lambda_function()
        self.create_deployment()    
        print(self.template.to_json())
    
    def create_lambda_function(self):
        variables = self.get_variables()
        print("lambda variables: {}".format(variables))
    # Create a Lambda function that will be mapped
        t = self.template
        code = ["def handler(event, context):\n    print('im a lambda')"]

    # Create a role for the lambda function
        t.add_resource(Role(
            "LambdaExecutionRole",
            Path="/",
            Policies=[Policy(
                PolicyName="root",
                PolicyDocument={
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Action": ["logs:*"],
                        "Resource": "arn:aws:logs:*:*:*",
                        "Effect": "Allow"
                    }, {
                        "Action": ["lambda:*"],
                        "Resource": "*",
                        "Effect": "Allow"
                    }]
                })],
            AssumeRolePolicyDocument={"Version": "2012-10-17", "Statement": [
                {
                    "Action": ["sts:AssumeRole"],
                    "Effect": "Allow",
                    "Principal": {
                        "Service": [
                            "lambda.amazonaws.com",
                            "apigateway.amazonaws.com"
                        ]
                    }
                }
            ]},
        ))

        # Create the Lambda function
        foobar_function = t.add_resource(Function(
            variables['FunctionName'],
            Code=Code(
                ZipFile=Join("", code)
            ),
            Handler=variables['handler'],
            Role=GetAtt("LambdaExecutionRole", "Arn"),
            Runtime=variables['runtime'],
        ))

        # Create a resource to map the lambda function to
        resource = t.add_resource(Resource(
            "FoobarResource",
            RestApiId=Ref('ApiGateway'),
            PathPart=variables["pathpart"],
            ParentId=GetAtt("ApiGateway", "RootResourceId"),
        ))

    # Create a Lambda API method for the Lambda resource
    # this is what associates a pathpart with a lambda
        method = t.add_resource(Method(
            "LambdaMethod",
            DependsOn=variables['FunctionName'],
            RestApiId=Ref('ApiGateway'),
            AuthorizationType="NONE",
            ResourceId=Ref(resource),
            HttpMethod="GET",
            Integration=Integration(
                Credentials=GetAtt("LambdaExecutionRole", "Arn"),
                Type="AWS",
                IntegrationHttpMethod='POST',
                IntegrationResponses=[
                    IntegrationResponse(
                        StatusCode='200'
                    )
                ],
                Uri=Join("", [
                    "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/",
                    GetAtt(variables["FunctionName"], "Arn"),
                    "/invocations"
                ])
            ),
            MethodResponses=[
                MethodResponse(
                    "CatResponse",
                    StatusCode='200'
                )
            ]
        ))

# Create a deployment
    def create_deployment(self):
        t = self.template
        variables = self.get_variables()
        stage_name = 'v1'

        deployment = t.add_resource(Deployment(
            "%sDeployment" % stage_name,
            DependsOn="LambdaMethod",
            RestApiId=Ref("ApiGateway"),
        ))

        stage = t.add_resource(Stage(
            '%sStage' % stage_name,
            StageName=stage_name,
            RestApiId=Ref("ApiGateway"),
            DeploymentId=Ref(deployment)
        ))

        key = t.add_resource(ApiKey(
            "ApiKey",
            StageKeys=[StageKey(
                RestApiId=Ref("ApiGateway"),
                StageName=Ref(stage)
            )]
        ))

        # Create an API usage plan
        usagePlan = t.add_resource(UsagePlan(
            "ExampleUsagePlan",
            UsagePlanName="ExampleUsagePlan",
            Description="Example usage plan",
            Quota=QuotaSettings(
                Limit=50000,
                Period="MONTH"
            ),
            Throttle=ThrottleSettings(
                BurstLimit=500,
                RateLimit=5000
            ),
            ApiStages=[
                ApiStage(
                    ApiId=Ref("ApiGateway"),
                    Stage=Ref(stage)
                )]
        ))

        # tie the usage plan and key together
        usagePlanKey = t.add_resource(UsagePlanKey(
            "ExampleUsagePlanKey",
            KeyId=Ref(key),
            KeyType="API_KEY",
            UsagePlanId=Ref(usagePlan)
        ))

        # Add the deployment endpoint as an output
        t.add_output([
            Output(
                "ApiEndpoint",
                Value=Join("", [
                    "https://",
                    Ref("ApiGateway"),
                    ".execute-api.us-east-1.amazonaws.com/",
                    stage_name
                ]),
                Description="Endpoint for this stage of the api"
            ),
            Output(
                "ApiKey",
                Value=Ref(key),
                Description="API key"
            ),
        ])