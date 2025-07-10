#!/usr/bin/python
#-*- coding: latin-1 -*-
"""Contains imaging parameters like effective pixelsize, absorption
coefficient, ..."""
import numpy
class ImagingPars(object):
    """Base class for parameters of imaging system.

    @cvar description: descriptive name of settings, used for GUI selection.
    @cvar pixelsize: Size of area (in µm) which is imaged to one pixel of the cam.
    @cvar sigma0: cross section for light absorption
    """
    description = None
    #pixelsize = 1
    sigma0 = 1.356e-13 
    expansion_time = 20
    
    mass = 1.45e-25
    ODmax = 0 #maximum optical density
    #import_array = numpy.loadtxt('C:/Users/Lab/Desktop',skiprows = 1,dtype={'names':('variables','values'),'formats':('S15','f4')}) # in seconds
    t_exp = 1.0 #(71.0+import_array[2][1])*1e-6 #exposure time in seconds, taken from Cicero permanent variable + 71us delay in camera
    detuning = 0.0 # detuning in units of gamma
    gamma = 6.035e6 # in Hz
    Io = 0.8*(25/(numpy.pi*1.1286**2))#15mW per beam, 22.57mm diameter beams
    I_red = Io/1.75 # Io/I_sat taking I_sat =3.57mW/cm2
    qe = 0.3 # between 0.35 and 0.4 
    dO = 0.25*3.14*(2.54*2/30)**2 # with only one lens: 0.25*pi*(D/do)^2  

    def __str__(self):
        s = "%s, t_exp = %.1fms, OD_max = %.1f"%(
            self.description,
            self.expansion_time,
            self.ODmax)
        return s

class ImagingParsHorizontal(ImagingPars):
    description = "horizontal"
    pixelsize = 2.82 #6.9/2.45#2.587 # pixel size = 5.6/magnification;   guppy pro 031B 5.6um pixels  
    #    pixelsize = 3.45e-6*2 * 1e6 #pixelsize in µm
    
class ImagingParsVertical(ImagingPars):
    description = "vertical"
    pixelsize = 2.82 #2.587       # 1.55 for fiber bundle and 1.83 for free space
    # now is 2.0 11/04/2018 (jsc)
    
    #pixelsize = 3.45e-6*2 * 1e6 #pixelsize in µm

class ImagingParsBlueFox(ImagingPars):
    description = 'BlueFox'
    pixelsize = 7.4 #pixelsize in µm
