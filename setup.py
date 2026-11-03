from pathlib import Path

from setuptools import setup, find_packages

setup(
    name="qsm",
    version="0.2.0",
    description="qsm: Quantum Lua-like Language using Qiskit",
    long_description=Path(__file__).with_name("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/imluri/qsm",
    author="Astrixity",
    packages=find_packages(),
    install_requires=["qiskit>=1.2,<3", "qiskit-aer>=0.15,<1"],
    entry_points={
        "console_scripts": [
            "qsm = qsm.__main__:main"
        ]
    },
    python_requires=">=3.8",
)
