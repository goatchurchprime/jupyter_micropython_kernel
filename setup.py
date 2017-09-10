from setuptools import setup

setup(name='jupyter_micropython_kernel',
      version='0.1.0',
      description='External MicroPython kernel for Jupyter notebooks.',
      author='Tony DiCola, Julian Todd',
      author_email='julian@goatchurch.org.uk',
      url='https://github.com/goatchurchprime/jupyter_micropython_kernel',
      packages=['jupyter_micropython_kernel'],
      install_requires=['pyserial', 'pexpect']
     )
