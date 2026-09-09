# Connect MiraRouter

MiraRouter provides an OpenAI-compatible API.

## Get an API Key

1. Sign up and log in at [MiraRouter](https://mirarouter.com/).
2. Open the console, create an API key, and copy it. The full key is shown only once, so store it securely.

## Configure AstrBot

Open the AstrBot dashboard and go to **Providers → Add Provider Source → MiraRouter**. Enter the following values:

| Field         | Value                                         |
| ------------- | --------------------------------------------- |
| Provider Name | `MiraRouter`                                  |
| API Base URL  | `https://api.mirarouter.com/v1`               |
| API Key       | The API key created in the MiraRouter console |

AstrBot automatically adds the `X-APP-CODE: astrbot` identifier to MiraRouter requests.

Save the source, then add the models you want to use with their service-provided model IDs.

## Set as Default

Go to **Config → Provider Settings**, select the MiraRouter model you just added as the default chat model, and save the configuration.

For more details, see the [MiraRouter documentation](https://docs.mirarouter.com/).
