from setuptools import setup

setup(name='jupyter_micropython_kernel',
      version='0.1.0',
      description='External MicroPython kernel for Jupyter notebooks.',
      author='Tony DiCola',
      author_email='tdicola@adafruit.com',
      url='https://github.com/adafruit/jupyter_micropython_kernel',
      packages=['jupyter_micropython_kernel'],
      install_requires=['pyserial']
     )
