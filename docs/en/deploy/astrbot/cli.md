# Deploy AstrBot from Source Code

> [!WARNING]
> You are deploying this project directly from source code. This tutorial requires you to have some technical background.
>
> This tutorial assumes Python `3.14+` is already installed on your device.

## Download/Clone Repository

If you have `git` installed on your computer, you can download the source code with the following command:

```bash
git clone https://github.com/BegoniaHe/AstrBot.git
# The above code will pull the latest commit of the source code, if you need to pull the latest stable release version of the source code, you can use the following command:
# git clone --depth=1 --branch $(git ls-remote --tags --sort='-v:refname' https://github.com/BegoniaHe/AstrBot.git | head -n1 | awk -F/ '{print $3}') https://github.com/BegoniaHe/AstrBot.git
cd AstrBot
```

If you don't have `git` installed, please download and install it first.

Alternatively, download the source code directly from GitHub and extract it:

![image](https://files.astrbot.app/docs/source/images/cli/image.png)

## Install Dependencies and Run

::: details 【🥳Recommended】Use `uv` to Manage Dependencies

> If `uv` is not installed, please refer to [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) for installation.

2. Execute in terminal (in the AstrBot directory)

```bash
uv sync
uv run main.py
```

If you have already synced the environment and only want to restart quickly, you can use:

```bash
uv run --no-sync main.py
```

:::

::: details Install Dependencies with Python Built-in venv

In the AstrBot source code directory, run the following command in the terminal:

> If on Windows and you downloaded and extracted the source code directly, please open the extracted folder and enter in the address bar:
> ![image](https://files.astrbot.app/docs/source/images/cli/image-1.png)

```bash
python -m venv .venv
```

The above steps will create and activate a virtual environment (to avoid disrupting your local Python environment).

Next, install the dependencies with the following command, which may take some time:

Execute on Mac/Linux/WSL:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
python main.py
```

Execute on Windows:

```bash
.venv\Scripts\activate
python -m pip install -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
python main.py
```

:::

## 🎉 All Done

If everything goes well, you will see logs printed by AstrBot.

If there are no errors, AstrBot will print the WebUI URL and the initial credentials in the startup logs. By default the WebUI is available at `http://localhost:6185`.

> [!TIP]
> If you are deploying AstrBot on a server, you need to replace `localhost` with your server's IP address.
>
> New users must use the random password printed in the startup logs to log in for the first time. Use the username shown in the logs (usually `astrbot`) and change it after first login.

Next, you need to deploy any messaging platform to use AstrBot on that platform.
