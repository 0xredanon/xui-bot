from setuptools import setup, find_packages

setup(
    name="xui-bot",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot",
        "SQLAlchemy",
        "mysqlclient",
        "pytz",
        "psutil"
    ],
    python_requires=">=3.8",
) 