# test_bedrock_stream.py
import asyncio
import os
from dotenv import load_dotenv
from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.config import Config
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver


def _build_client() -> BedrockRuntimeClient:
    load_dotenv()
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        region = "us-east-1"
        print("⚠️  AWS_REGION no definido, usando us-east-1 por defecto")

    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    preview_key = f"{access_key[:4]}..." if access_key else "<no-key>"
    print(f"🔐 Credencial detectada: {preview_key} | Región: {region}")

    config = Config(
        region=region,
        endpoint_uri=f"https://bedrock-runtime.{region}.amazonaws.com",
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
    )
    return BedrockRuntimeClient(config=config)


async def main() -> None:
    client = _build_client()
    stream = await client.invoke_model_with_bidirectional_stream(
        InvokeModelWithBidirectionalStreamOperationInput(
            model_id="amazon.nova-sonic-v1:0"
        )
    )
    print("✅ Stream abierto:", stream)
    await stream.input_stream.close()

if __name__ == "__main__":
    asyncio.run(main())