"""setup.py: setuptools control."""
 
 
import re
from setuptools import setup
 
 
version = re.search(
    '^__version__\s*=\s*"(.*)"',
    open('deppth/deppth.py').read(),
    re.M
    ).group(1)
 
 
with open("README.md", "rb") as f:
    long_descr = f.read().decode("utf-8")
 
 
setup(
    name = "deppth",
    packages = ["deppth"],
    entry_points = {
        "console_scripts": ['deppth = deppth.deppth:main']
        },
    version = version,
    description = "Decompress, Extract, and Pack for Pyre, Transistor, and Hades",
    long_description = long_descr,
    author = "Neil Sandberg",
    author_email = "neil.sandberg@gmail.com",
    url = "",
    )