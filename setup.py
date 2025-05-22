from setuptools import setup, find_packages

setup(
    name="xui-bot",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "pyTelegramBotAPI>=4.12.0",
        "SQLAlchemy>=1.4.0",
        "pytest>=7.4.3",
        "pytest-cov>=4.1.0"
    ]
) 