import setuptools

with open("README.rst", "r") as fh:
    long_description = fh.read()

print(long_description)

setuptools.setup(
    name="cocotbext-wishbone",
    use_scm_version={
        "relative_to": __file__,
        "write_to": "cocotbext/wishbone/version.py",
    },
    author="Staf Verhaegen, Mathias Kreider",
    author_email="staf@stafverhaegen.be, m.kreider@gsi.de",
    description="Cocotb Wishbone modules",
    packages=["cocotbext.wishbone"],
    install_requires=['cocotb'],
    setup_requires=[
        'setuptools_scm',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    ],
)
