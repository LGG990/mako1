#!/usr/bin/python
#-*- coding: latin-1 -*-
"""Module for fitting routines and representation of fit results.
@group fit routines: Fitting NoFit Gauss2d GaussSym2d GaussBose2d Bimodal2d BoseBimodal2d ThomasFermi2d
@sort: Fitting NoFit Gauss2d GaussSym2d GaussBose2d Bimodal2d BoseBimodal2d ThomasFermi2d  
@group fit result objects: FitPars FitParsNoFit FitParsGauss2d FitParsBimodal2d FitParsTF2d
@sort: FitPars FitParsNoFit FitParsGauss2d FitParsTF2d FitParsBimodal2d
"""


use_minpack = False
if use_minpack:
    from scipy.optimize import leastsq

import numpy
#import scipy.special

import LM
reload(LM)

import sys
from time import clock as time
imgtype = numpy.float32

def pickpeak(x, npicks=5, rdiff = 5):
    """
Search for peaks in data. Reurn arrays may contain NaN, e.g., if less peaks than required are found. 
@param x: data sequence
@type x: ndarray
@param npicks: number of peaks to return.
@param rdiff: minimum spacing (in data points) between two peaks
@return: tuple of ndarray.
@rtype: (peak values, peak locations)
"""

    #initialize result values with NaN
    vals = numpy.array([numpy.NaN]*npicks)
    loc  = numpy.array([0]*npicks)

    rmin = numpy.nanmin(x)-1
    dx = numpy.diff(numpy.r_[rmin, x, rmin])
    
    # find position and their values of peaks (local maxima) 
    pos_peaks, = numpy.nonzero((dx[0:-1]>=0.0) & (dx[1:]<=0.0)) 
    val_peaks  = x[pos_peaks] #corresponding
    
    # select peaks in descending order, seperated by at least rdiff
  
    for i in range(npicks):

        mi = numpy.nanargmax(val_peaks) #find index of largest peak
        #mi = numpy.nanargmax(pos_peaks)
        peakval = val_peaks[mi]
        peakpos = pos_peaks[mi]

        vals[i] = peakval
        loc[i]  = peakpos

        # for next iteration: only keep peaks at least rdiff points
        # distance from last peak
        ind = numpy.nonzero(abs(pos_peaks - peakpos) > rdiff)
        if len(ind) == 0: #nothing left!
            break
        val_peaks = val_peaks[ind]
        pos_peaks = pos_peaks[ind]
        if numpy.isfinite(val_peaks).sum() == 0: 
            break

    return vals, loc

class Fitting(object):
    """Base class for fitting. Provides common interface for handling
    of imaging parameters.

    @ivar imaging_pars: contains imaging parameters like, e.g.,
    magnification, absorption coefficient.

    @type imaging_pars: L{ImagingPars}"""
    
    imaging_pars = None
    verbose = False
    
    def set_imaging_pars(self, ip):
        self.imaging_pars = ip

    def do_fit(self, img, roi):
        """perform fitting.

        @param img:
        @type img: 2d ndarray

        @param roi: region of interest (ROI) if image, where to perform fitting.
        @type roi: L{ROI}

        @return: [fit image,...], fit background, FitPars
        @rtype: [ndarray,...], ndarray, L{FitPars}
        """
    
    
    def fJ_masked(self, pars, x, y, v0=0, sel = None):
        """
        ignore masked values in v0. somewhat specialized for 2d fitting functions
        """
        f, J = self.fJ(pars, x, y, v0)

        if sel is None:
            sel = numpy.ma.getmaskarray(v0.ravel())
        
        f[sel] = 0
        J[:,sel] = 0
        return f, J

class NoFit(Fitting):
    """Performs no fit."""
    def __init__(self, imaging_pars=None):
        self.imaging_pars = imaging_pars

    def do_fit(self, img, roi):
        background = numpy.array([0.0], dtype = imgtype)
        return [], background, FitParsNoFit()
######Original Gauss 2d class#######################
class Gauss2d(Fitting):
    """Perform fit of 2d Gaussian to data.
    @sort: do_fit, gauss1d, Dgauss1d, gauss2d, gauss2d_flat, Dgauss2d
    """

    def __init__(self, imaging_pars=None):
        """Constructor.
        
        @type imaging_pars: L{ImagingPars}
        """

        self.imaging_pars = imaging_pars
        self.cache = {}

    def gauss1d(self, pars, x, v0 = 0):
        """calculate 1d gaussian.
        @return: difference of 1d gaussian and reference (data) values
        @param pars: parameters of gaussian. see source.
        @param x: x values
        @param v0: reference value
        """
        A, m, s, offs = pars[0:4]
        v = A*numpy.exp(- (x-m)**2 / (2*s**2)) + offs
        return v-v0

    def Dgauss1d(self, pars, x, v=0):
        """
        calculated Jacobian matrix for 1d gauss
        """
        A, m, s, offs = pars[0:4]
        f = A*numpy.exp( - (x-m)**2 / (2*s**2))
        J = numpy.empty(shape = (4,)+x.shape, dtype = imgtype)
        J[0] = 1.0/A * f
        J[1] = f*(x-m)/s**2
        J[2] = f*(x-m)**2/s**3
        J[3] = 1
        return J

    def fJgauss1d(self, pars, x, v = 0):
        A, m, s, offs = pars[0:4]
        f = A*numpy.exp( - (x-m)**2 / (2*s**2))
        if 1:
            J = numpy.empty(shape = (4,)+x.shape, dtype = imgtype)
            J[0] = 1.0/A * f
            J[1] = f*(x-m)/s**2
            J[2] = f*(x-m)**2/s**3
            J[3] = 1
            return f + (offs - v), J
        return f + (offs - v)

    def gauss2d(self, pars, x, y, v0=0):
        """calculate 2d gaussian. uses caching strategy.

        @rtype: 2d ndarray (MxN)
        @param pars: see source
        @param x: x values
        @type x: ndarray (1xM row vector)
        @param y: y values
        @type y: ndarray (Nx1 column vector)
        @param v0: reference value
        @type v0: 2d ndarray (MxN) or scalar
        """
        A, mx, my, sx, sy, offs = pars[0:6]

        key = (A, mx, my, sx, sy)
        if self.cache.has_key(key):
            v = self.cache[key]
        else:
            v = A*numpy.exp( - (x-mx)**2 / (2*sx**2) 
                       - (y-my)**2 / (2*sy**2))
            self.cache.clear()
            #caching in effect only for calculating of Jacobi, clear
            #cache after result has been retrieved to avoid excessive
            #memory use
            self.cache[key] = v
            
        return v + (offs - v0)

    def gauss2d_flat(self, pars, x, y, v0=0):
        """return flattened result of L{gauss2d}"""
        return self.gauss2d(pars, x, y, v0).reshape((-1,))
    
    def Dgauss2d(self, pars, x, y, v=0):
        """calculate Jacobian for 2d gaussian.
        @rtype: 2d ndarray (see source)
        """
        A, mx, my, sx, sy, offs = pars[0:6]

        f = self.gauss2d([A, mx, my, sx, sy, 0], x, y)

        J = numpy.empty(shape = (6,) + f.shape, dtype = imgtype) 
        J[0] = 1.0/A * f
        J[1] = f*(x-mx)/sx**2
        J[2] = f*(y-my)/sy**2
        J[3] = f*(x-mx)**2/sx**3
        J[4] = f*(y-my)**2/sy**3
        J[5] = 1

        return J.reshape((6,-1))

    def fJ(self, pars, x, y, v0=0):
        A, mx, my, sx, sy, offs = pars[0:6]

        f = A*numpy.exp( - (x-mx)**2 / (2*sx**2) 
                         - (y-my)**2 / (2*sy**2))
        
        J = numpy.empty(shape = (6,) + f.shape, dtype = imgtype)
        J[0] = 1.0/A * f
        J[1] = f*(x-mx)/sx**2
        J[2] = f*(y-my)/sy**2
        J[3] = f*(x-mx)**2/sx**3
        J[4] = f*(y-my)**2/sy**3
        J[5] = 1

        f += offs
        f -= v0
        f.shape = (-1,)
        J.shape = (6,-1)
        return f, J

    

    def _find_startpar_gauss(self, x, prof):
        """
        find good initial estimates for fit parameters based on
        horizontal or vertical profiles
        
        @param x: x or y values
        @param prof: horizontal of vertical profiles
        @return: [A, mu, sigma, offset]
        """
        
        Nsh = 20 # number (half) of points for smoothing
        gs  = Nsh/2 # width gaussian
        
        #use gaussian for smoothing
        gx = numpy.arange(2*Nsh+1, dtype = imgtype) - Nsh
        gy = numpy.exp(-gx**2/gs**2)
        gy/= gy.sum()

        #smooth profil, limit axes to valid values
        profsmooth = numpy.convolve(prof, gy, mode = 'valid')
        xs = x[Nsh:-Nsh]
        #TODO: ensure enough points (>3?)

        #estimate peak position and fwhm width
        peakval, peakpos = pickpeak(profsmooth, 1)

        try:
            halfval, halfpos = pickpeak(
                -numpy.abs(profsmooth - (peakval + numpy.nanmin(profsmooth))/2.0),
                npicks = 2)
            width = numpy.abs(numpy.diff(xs[halfpos]))
        except:
            print "Warning: can't determine initial guess for width", sys.exc_info()
            width = 50

        off = numpy.nanmin(profsmooth) #TODO: can we do better (robust?)
        try:
            m = xs[peakpos]
        except IndexError:
            m = 0.5*(x[0] + x[-1])
            
        s = width
        A = peakval - off

        #make gaussian fit
        startpars = numpy.r_[A, m, s, off]

        if use_minpack:
            fitpar, foo = leastsq(self.gauss1d,
                                   startpars,
                                   args = (x, prof),
                                   Dfun = self.Dgauss1d, col_deriv = 1,
                                   maxfev = 30,
                                   ftol = 1e-4
                                   )
        else:
            fitpar = LM.LM(self.fJgauss1d,
                        startpars,
                        args = (x, prof),
                        kmax = 30,
                        eps1 = 1e-6,
                        eps2 = 1e-6,
                        verbose = self.verbose,
                        )
        return fitpar


    def do_fit(self,img, roi):
        x = numpy.asarray(roi.xrange_clipped(img), dtype = imgtype)
        y = numpy.asarray(roi.yrange_clipped(img), dtype = imgtype)


        imgroi = img[roi.y, roi.x]
        try:
            imgroifilled = imgroi.filled()
        except AttributeError:
            imgroifilled = imgroi

        xprof = imgroifilled.sum(0)
        yprof = imgroifilled.sum(1)

        try:
            startparx = self._find_startpar_gauss(x,xprof)
            startpary = self._find_startpar_gauss(y,yprof)
        except Exception:
            startparx = numpy.array([1, 100, 100, 10, 10, 0])
            startpary = numpy.array([1, 100, 100, 10, 10, 0])
            print "Warning: can't determine initial guess for fitting parameters"
        
        startpar = numpy.array([startparx[0]/(startpary[2]*numpy.sqrt(2*numpy.pi)),
                                startparx[1], #m_x
                                startpary[1], #m_y
                                startparx[2], #sigma_x
                                startpary[2], #sigma_y
                                0 #offset
                                ])

        x.shape = (1,-1)
        y.shape = (-1, 1)

        
        if use_minpack:
            fitpar, cov_x, infodict, mesg, ier = \
                leastsq(self.gauss2d_flat, 
                        startpar, 
                        args=(x,y, imgroi),
                        Dfun = self.Dgauss2d, col_deriv=1,
                        maxfev = 50, 
                        ftol = 1e-6,
                        full_output=1, 
                        )
        else:
            imgsel = numpy.ma.getmaskarray(imgroi.ravel())
            fitpar, J, r = LM.LM(self.fJ_masked,
                                 startpar,
                                 args = (x, y, imgroi, imgsel),
                                 kmax = 30,
                                 eps1 = 1e-6,
                                 eps2 = 1e-6,
                                 verbose = self.verbose,
                                 full_output = True,
                                 )
        fitparerr, sigma = LM.fitparerror(fitpar, J, r)
                       
        imgfit = self.gauss2d(fitpar, x, y)
        
        Counts = yprof.sum()#this cant be right for the area under a 2d gaussian... 
        #just the y profile??? I tried xprof*yprof but result is too large.
        fitpars = FitParsGauss2d(fitpar, self.imaging_pars, fitparerr, sigma, Counts)

        #validity check
        A, mx, my, sx, sy, offs = fitpar[0:6]
        A, sx, sy = abs(A), abs(sx), abs(sy)
        if A<0:
            fitpars.invalidate()
        if mx < roi.xmin - 100 or mx > roi.xmax + 100:
            fitpars.invalidate()
        if my < roi.ymin - 100 or my > roi.ymax + 100:
            fitpars.invalidate()
        if sx > 3*abs(roi.xmax - roi.xmin) or \
           sy > 3*abs(roi.ymax - roi.ymin):
            fitpars.invalidate()

        background = numpy.array([fitpars.offset], dtype = imgtype)
        return [imgfit,], background, fitpars
##########End of original Gauss 2D class###########
        
class FluorescenceGauss(Fitting):
    """Perform fit of 2d Gaussian to data.
    @sort: do_fit, gauss1d, Dgauss1d, gauss2d, gauss2d_flat, Dgauss2d
    """

    def __init__(self, imaging_pars=None):
        """Constructor.
        
        @type imaging_pars: L{ImagingPars}
        """

        self.imaging_pars = imaging_pars
        self.cache = {}

    def gauss1d(self, pars, x, v0 = 0):
        """calculate 1d gaussian.
        @return: difference of 1d gaussian and reference (data) values
        @param pars: parameters of gaussian. see source.
        @param x: x values
        @param v0: reference value
        """
        A, m, s, offs = pars[0:4]
        v = A*numpy.exp(- (x-m)**2 / (2*s**2)) + offs
        return v-v0


    def fJgauss1d(self, pars, x, v = 0):
        A1,A2,m1,m2,s1,s2,offs = pars[0:7]
        f = A1*numpy.exp( - (x-m1)**2 / (2*s1**2))+ A2*numpy.exp( - (x-m2)**2 / (2*s2*2))
        
        if 1:
            J = numpy.empty(shape = (7,)+x.shape, dtype = imgtype)
            J[0] = 1.0/A1 * f
            J[1] = 1.0/A2 * f
            J[2] = f*(x-m1)/s1**2
            J[3] = f*(x-m2)/s2**2
            J[4] = f*(x-m1)**2/s1**3
            J[5] = f*(x-m2)**2/s2**3
            J[6] = 1
            return f + (offs - v), J
        return f + (offs - v)

    def gauss2d(self, pars, x, y, v0=0):
        """calculate 2d gaussian. uses caching strategy.

        @rtype: 2d ndarray (MxN)
        @param pars: see source
        @param x: x values
        @type x: ndarray (1xM row vector)
        @param y: y values
        @type y: ndarray (Nx1 column vector)
        @param v0: reference value
        @type v0: 2d ndarray (MxN) or scalar
        """
        A1,A2,m1x,m2x,m1y,m2y,s1x,s2x,s1y,s2y,offs = pars[0:11]

        key = (A1,A2, m1x,m2x, m1y,m2y, s1x,s2x, s1y,s2y)
        if self.cache.has_key(key):
            v = self.cache[key]
        else:
            v = A1*numpy.exp( - (x-m1x)**2 / (2*s1x**2) 
                         - (y-m1y)**2 / (2*s1y**2)) + A2*numpy.exp( - (x-m2x)**2 / (2*s2x**2) 
                         - (y-m2y)**2 / (2*s2y**2))
            self.cache.clear()
            #caching in effect only for calculating of Jacobi, clear
            #cache after result has been retrieved to avoid excessive
            #memory use
            self.cache[key] = v
            
        return v + (offs - v0)

                                
    def fJ(self, pars, x, y, v0=0):
        A1,A2,m1x,m2x,m1y,m2y,s1x,s2x,s1y,s2y,offs = pars[0:11]

        f = A1*numpy.exp( - (x-m1x)**2 / (2*s1x**2) 
                         - (y-m1y)**2 / (2*s1y**2)) + A2*numpy.exp( - (x-m2x)**2 / (2*s2x**2) 
                         - (y-m2y)**2 / (2*s2y**2))
        f1zz = A1*numpy.exp( - (x-m1x)**2 / (2*s1x**2) 
                         - (y-m1y)**2 / (2*s1y**2))
        f2zz = A2*numpy.exp( - (x-m2x)**2 / (2*s2x**2) 
                         - (y-m2y)**2 / (2*s2y**2))
        
        J = numpy.empty(shape = (11,) + f.shape, dtype = imgtype)
        J[0] = 1.0/A1 * f1zz
        J[1] = 1.0/A2 * f2zz
        J[2] = f1zz*(x-m1x)/s1x**2
        J[3] = f2zz*(x-m2x)/s2x**2
        J[4] = f1zz*(y-m1y)/s1y**2
        J[5] = f2zz*(y-m2y)/s2y**2
        J[6] = f1zz*(x-m1x)**2/s1x**3
        J[7] = f2zz*(x-m2x)**2/s2x**3
        J[8] = f1zz*(y-m1y)**2/s1y**3
        J[9] = f2zz*(y-m2y)**2/s2y**3
        J[10] = 1

        f += offs
        f -= v0
        f.shape = (-1,)
        J.shape = (11,-1)
        return f, J

    

    def _find_startpar_gauss(self, x, prof):
        """
        find good initial estimates for fit parameters based on
        horizontal or vertical profiles
        
        @param x: x or y values
        @param prof: horizontal of vertical profiles
        @return: [A, mu, sigma, offset]
        """
        
        Nsh = 20 # number (half) of points for smoothing
        gs  = Nsh/2 # width gaussian
        
        #use gaussian for smoothing
        gx = numpy.arange(2*Nsh+1, dtype = imgtype) - Nsh
        gy = numpy.exp(-gx**2/gs**2)
        gy/= gy.sum()

        #smooth profil, limit axes to valid values
        profsmooth = numpy.convolve(prof, gy, mode = 'valid')
        xs = x[Nsh:-Nsh]
        #TODO: ensure enough points (>3?)

        #estimate peak position and fwhm width
        peakval, peakpos = pickpeak(profsmooth, 2)

        try:
            halfval1, halfpos1 = pickpeak(
                -numpy.abs(profsmooth - (peakval[0] + numpy.nanmin(profsmooth))/2.0),
                npicks = 2)
            halfval2, halfpos2 = pickpeak(
                -numpy.abs(profsmooth - (peakval[1] + numpy.nanmin(profsmooth))/2.0),
                npicks = 2)
            width1 = numpy.abs(numpy.diff(xs[halfpos1]))
            width2 = numpy.abs(numpy.diff(xs[halfpos2]))
            
        except:
            print "Warning: can't determine initial guess for width", sys.exc_info()
            width1 = 20
            width2 = 20

        off = numpy.nanmin(profsmooth) #TODO: can we do better (robust?)
        
        try:
                        
            m1 = xs[peakpos[0]]
            m2 = xs[peakpos[1]]
        except IndexError:
            m1 = 0.33*(x[0] + x[-1])
            m2 = 0.66*(x[0] + x[-1])
        
        #m1 = m1 = 0.33*(x[0] + x[-1])
        #m2 = 0.66*(x[0] + x[-1])
        
        s1 = width1
        s2 = width2
        
        A1 = peakval[0] - off
        A2 = peakval[1] - off

        #make gaussian fit
        startpars = numpy.r_[A1,A2,m1,m2,s1,s2,off]
        print ('Hello its me')
        print (startpars)
        fitpar = LM.LM(self.fJgauss1d,
                        startpars,
                        args = (x, prof),
                        kmax = 30,
                        eps1 = 1e-6,
                        eps2 = 1e-6,
                        verbose = self.verbose,
                        )
        
        return fitpar


    def do_fit(self,img, roi):
        x = numpy.asarray(roi.xrange_clipped(img), dtype = imgtype)
        y = numpy.asarray(roi.yrange_clipped(img), dtype = imgtype)


        imgroi = img[roi.y, roi.x]
        try:
            imgroifilled = imgroi.filled()
        except AttributeError:
            imgroifilled = imgroi

        xprof = imgroifilled.sum(0)
        yprof = imgroifilled.sum(1)

        try:
            startparx = self._find_startpar_gauss(x,xprof)
            startpary = self._find_startpar_gauss(y,yprof)
            print('Ojo al dato')
            print (startparx)
            print (startpary)
            
            pp1x = startparx[2]
            pp2x = startparx[3]
            if (pp1x>pp2x):
                startparx[2],startparx[3] = startparx[3],startparx[2]
                startparx[0],startparx[1] = startparx[1],startparx[0]
                startpary[2],startpary[3] = startpary[3],startpary[2]
                startpary[0],startpary[1] = startpary[1],startpary[0]
                #print('I did swaped my values')
                #print(startparx)
                #print(startpary)
            else:
                #print('Everything was in order my colonel')
                startparx = startparx
                startpary = startpary
                
            #inds = peakpos.argsort()
            #peakval = peakval_[inds]
            #peakpos = peakpos_.sort()
            
        except Exception:
            startparx = numpy.array([100,100, 100, 220, 15, 20, 100])
            startpary = numpy.array([100,100, 100, 220, 15, 20, 100])
            print "Warning: can't determine initial guess for fitting parameters"
        
        startpar = numpy.array([startparx[0]/(startpary[4]*numpy.sqrt(2*numpy.pi)), #A1
                                startparx[1]/(startpary[5]*numpy.sqrt(2*numpy.pi)), #A2
                                startparx[2], #m1_x
                                startparx[3], #m2_x
                                startpary[2], #m1_y
                                startpary[3], #m2_y
                                startparx[4], #sigma1_x
                                startparx[5], #sigma2_x
                                startpary[4], #sigma1_y
                                startpary[5], #sigma2_y
                                0 #offset
                                ])
        x.shape = (1,-1)
        y.shape = (-1, 1)

        
        
        imgsel = numpy.ma.getmaskarray(imgroi.ravel())
        fitpar, J, r = LM.LM(self.fJ_masked,
                                 startpar,
                                 args = (x, y, imgroi, imgsel),
                                 kmax = 50,
                                 eps1 = 1e-6,
                                 eps2 = 1e-6,
                                 verbose = self.verbose,
                                 full_output = True,
                                 )
        fitparerr, sigma = LM.fitparerror(fitpar, J, r)
                       
        imgfit = self.gauss2d(fitpar, x, y)
        
        Counts = 30.
        fitpars = FitParsFluorescenceGauss(fitpar, self.imaging_pars, fitparerr, sigma, Counts)
        
        '''
        #validity check
        A, mx, my, sx, sy, offs = fitpar[0:6]
        A, sx, sy = abs(A), abs(sx), abs(sy)
        if A<0:
            fitpars.invalidate()
        if mx < roi.xmin - 100 or mx > roi.xmax + 100:
            fitpars.invalidate()
        if my < roi.ymin - 100 or my > roi.ymax + 100:
            fitpars.invalidate()
        if sx > 3*abs(roi.xmax - roi.xmin) or \
           sy > 3*abs(roi.ymax - roi.ymin):
            fitpars.invalidate()
        '''
        background = numpy.array([fitpars.offset], dtype = imgtype)
        return [imgfit,], background, fitpars
        
##################End of Duplicate of Gauss 2d Class######################
class GaussBose2d(Gauss2d):
    """Perform fit of bose enhanced gaussian distribution,
    
    @sort: do_fit, gaussbose2d, gaussbose2d_flat, rF, fJr"""

    def __init__(self, imaging_pars = None):
        super(GaussBose2d, self).__init__(imaging_pars)
        self.MyFitPars = FitParsGaussBose2d

    def gaussbose2d(self, pars, x, y, v0 = 0):
        """calculate 2d bose enhanced gaussian distribution. See L{gauss2d} for
        parameter description.
        """
        A, mx, my, sx, sy, offs = pars[0:6]

        key = (A, mx, my, sx, sy)

        if self.cache.has_key(key):
            g = self.cache[key]
        else:
            g = numpy.exp(- (x-mx)**2 / (2*sx**2) 
                          - (y-my)**2 / (2*sy**2))
            g2(g,g)
            numpy.multiply(g, A, g)
            
        return g + offs - v0

    def gaussbose2d_flat(self, pars, x, y, v0=0):
        return self.gaussbose2d(pars, x, y, v0).reshape((-1,))

    def rF(self, pars, x, y):
        """
        calculate seperately nonlinear functions and the derivatives (reduced problem)
        """
        
        mx, my, sx, sy = pars

        X,Y = numpy.broadcast_arrays(x,y)
        F = numpy.empty(shape = (2,) + X.shape)

        #gauss
        numpy.multiply(numpy.exp( -(x-mx)**2/(2*sx**2)),
                       numpy.exp( -(y-my)**2/(2*sy**2)),
                       F[0])
        G = F[0].copy()
        g2(F[0], F[0])
        dg2G = dg2(G)

        #offset
        F[1] = 1

        #derivatives
        Fd = []

        #mx
        Fdmx = numpy.empty_like(F)
        numpy.multiply(G, 1.0/(sx**2)*(x-mx), Fdmx[0])
        numpy.multiply(Fdmx[0], dg2G, Fdmx[0])
        Fdmx[1] = 0

        #my
        Fdmy = numpy.empty_like(F)
        numpy.multiply(G, 1.0/(sy**2)*(y-my), Fdmy[0])
        numpy.multiply(Fdmy[0], dg2G, Fdmy[0])
        Fdmy[1] = 0

        #sx
        Fdsx = numpy.empty_like(F)
        numpy.multiply(G, 1.0/sx**3 * ((x-mx)**2), Fdsx[0])
        numpy.multiply(Fdsx[0], dg2G, Fdsx[0])
        Fdsx[1] = 0

        #sy
        Fdsy = numpy.empty_like(F)
        numpy.multiply(G, 1.0/sy**3 * ((y-my)**2), Fdsy[0])
        numpy.multiply(Fdsy[0], dg2G, Fdsy[0])
        Fdsy[1] = 0

        Fd = [Fdmx, Fdmy, Fdsx, Fdsy]
        nz = [slice(0,1), slice(0,1), slice(0,1), slice(0,1)] #non zero pages of Fd[i] 

        F.shape = (F.shape[0], -1)

        for A in Fd:
            A.shape = (A.shape[0], -1)

        return F, Fd, nz

    def fJr(self, pars, x, y, vin = 0, sel = None, calcJ = True):
        """
        calculate f and J for reduced system (only nonlinear parameters)
        """

        F, Fd, nz = self.rF(pars, x, y)
        v = numpy.ravel(vin)

        #calculate linear Parameters
        FtF = numpy.inner(F, F)
        Fty = numpy.inner(F, v)
        try:
            c = numpy.linalg.solve(FtF, Fty)
        except numpy.linalg.LinAlgError:
            print "normal equations numpy.singular, retrying"
            c, res, rank, s = numpy.linalg.lstsq(F.transpose(),v)

        #calculate residuum
        r = numpy.dot(c, F) - v

        if not calcJ:
            return r, c, F

        ##calculate complete Jacobian
        cd = numpy.empty(shape = (len(pars),) + c.shape)
        Jr = numpy.empty(shape = (len(pars),) + F.shape[1:])

        for j in range(len(pars)):
            cFdj = numpy.dot(c[nz[j]], Fd[j][nz[j]])

            #rm = numpy.inner(Fd[j], r) - numpy.inner(F, cFdj) #expensive
            rm = numpy.zeros(shape = Fd[j].shape[0])
            rmnz = numpy.inner(Fd[j][nz[j]], r)
            rm[nz[j]] = rmnz
            rm -= numpy.inner(F, cFdj) #expensive
            try:
                cd[j] = numpy.linalg.solve(FtF, rm) #cheap
            except numpy.linalg.LinAlgError:
                print "numpy.singular matrix in complete Jacobian, retrying"
                cdj, res, rank, s = numpy.linalg.lstsq(F.transpose(), cFdj)
                cd[j] = -cdj
                
            Jr[j] = cFdj + numpy.dot(cd[j], F) #expensive!

        if sel is None:
            sel = numpy.ma.getmaskarray(v)
        r[sel] = 0
        Jr[:,sel] = 0

        return r, Jr


    def do_fit(self,img, roi):
        x = numpy.asarray(roi.xrange_clipped(img), dtype = imgtype)
        y = numpy.asarray(roi.yrange_clipped(img), dtype = imgtype)

        imgroi = img[roi.y, roi.x]
        try:
            imgroifilled = imgroi.filled()
        except AttributeError:
            imgroifilled = imgroi

        xprof = imgroifilled.sum(0)
        yprof = imgroifilled.sum(1)

        try:
            startparx = self._find_startpar_gauss(x,xprof)
            startpary = self._find_startpar_gauss(y,yprof)
        except Exception:
            startparx = numpy.array([1, 100, 100, 10, 10, 0])
            startpary = numpy.array([1, 100, 100, 10, 10, 0])
            print "Warning: can't determine initial guess for fitting parameters"
        
        startpar = numpy.array([startparx[0]/(startpary[2]*numpy.sqrt(2*numpy.pi)),
                                startparx[1], #m_x
                                startpary[1], #m_y
                                startparx[2], #sigma_x
                                startpary[2], #sigma_y
                                0 #offset
                                ])

        x.shape = (1,-1)
        y.shape = (-1, 1)
    

        imgsel = numpy.ma.getmaskarray(imgroi.ravel())
                
        p, J, f = LM.LM(self.fJr,
                        startpar[1:-1],
                        args = (x,y,imgroi,imgsel),
                        kmax = 30,
                        eps1 = 1e-5,
                        eps2 = 5e-5,
                        tau = 1e-3,
                        verbose = self.verbose,
                        full_output = True)
                    #TODO: check for fit succeed
        r,c,F = self.fJr(p,x,y,imgroi, calcJ = False)
        fitpar = numpy.array([c[0], p[0], p[1], p[2], p[3], c[1]])
        
        Jfull = numpy.vstack((F, J))
        cepe, sigma = LM.fitparerror( numpy.hstack((c, p)), Jfull, r)
        ce, pe = cepe[:2], cepe[2:]
        fitparerr = numpy.array([ce[0],
                                 pe[0], pe[1], pe[2], pe[3],
                                 ce[1]])

        imgfit = self.gaussbose2d(fitpar, x, y)

        fitpars = FitParsGaussBose2d(fitpar, self.imaging_pars, fitparerr, sigma)

        #validity check
        A, mx, my, sx, sy, offs = fitpar[0:6]
        A, sx, sy = abs(A), abs(sx), abs(sy)
        if A<0:
            fitpars.invalidate()
        if mx < roi.xmin - 100 or mx > roi.xmax + 100:
            fitpars.invalidate()
        if my < roi.ymin - 100 or my > roi.ymax + 100:
            fitpars.invalidate()
        if sx > 3*abs(roi.xmax - roi.xmin) or \
           sy > 3*abs(roi.ymax - roi.ymin):
            fitpars.invalidate()

        background = numpy.array([fitpars.offset], dtype = imgtype)
        return [imgfit,], background, fitpars


class GaussSym2d(Fitting):
    """Perform fit of 2d symmetric Gaussian to data.
    @sort: do_fit, fJgauss1d, gauss2d, gauss2d_flat, fJgauss2d
    """

    def __init__(self, imaging_pars=None):
        """Constructor.
        
        @type imaging_pars: L{ImagingPars}
        """

        self.imaging_pars = imaging_pars
        self.cache = {}

    def fJgauss1d(self, pars, x, v = 0):
        A, m, s, offs = pars[0:4]
        f = A*numpy.exp( - (x-m)**2 / (2*s**2))
        if 1:
            J = numpy.empty(shape = (4,)+x.shape, dtype = imgtype)
            J[0] = 1.0/A * f
            J[1] = f*(x-m)/s**2
            J[2] = f*(x-m)**2/s**3
            J[3] = 1
            return f + (offs - v), J
        return f + (offs - v)

    def gauss2d(self, pars, x, y, v0=0):
        """calculate 2d gaussian. uses caching strategy.

        @rtype: 2d ndarray (MxN)
        @param pars: see source
        @param x: x values
        @type x: ndarray (1xM row vector)
        @param y: y values
        @type y: ndarray (Nx1 column vector)
        @param v0: reference value
        @type v0: 2d ndarray (MxN) or scalar
        """
        A, mx, my, s, offs = pars[0:5]

        key = (A, mx, my, s)
        if self.cache.has_key(key):
            v = self.cache[key]
        else:
            v = A*numpy.exp( - (x-mx)**2 / (2*s**2) 
                       - (y-my)**2 / (2*s**2))
            self.cache.clear()
            #caching in effect only for calculating of Jacobi, clear
            #cache after result has been retrieved to avoid excessive
            #memory use
            self.cache[key] = v
            
        return v + (offs - v0)

    def gauss2d_flat(self, pars, x, y, v0=0):
        """return flattened result of L{gauss2d}"""
        return self.gauss2d(pars, x, y, v0).reshape((-1,))
    
    def fJ(self, pars, x, y, v0=0):
        A, mx, my, s, offs = pars[0:5]

        f = A*numpy.exp( - (x-mx)**2 / (2*s**2) 
                         - (y-my)**2 / (2*s**2))
        
        J = numpy.empty(shape = (5,) + f.shape, dtype = imgtype)
        J[0] = 1.0/A * f
        J[1] = f*(x-mx)/s**2
        J[2] = f*(y-my)/s**2
        J[3] = f*( (x-mx)**2/s**3 + (y-my)**2/s**3) #TODO: nachrechnen
        J[4] = 1

        f += offs
        f -= v0
        f.shape = (-1,)
        J.shape = (5,-1)
        return f, J

    def _find_startpar_gauss(self, x, prof):
        """
        find good initial estimates for fit parameters based on
        horizontal or vertical profiles
        
        @param x: x or y values
        @param prof: horizontal of vertical profiles
        @return: [A, mu, sigma, offset]
        """
        
        Nsh = 20 # number (half) of points for smoothing
        gs  = Nsh/2 # width gaussian
        
        #use gaussian for smoothing
        gx = numpy.arange(2*Nsh+1, dtype = imgtype) - Nsh
        gy = numpy.exp(-gx**2/gs**2)
        gy/= gy.sum()

        #smooth profil, limit axes to valid values
        profsmooth = numpy.convolve(prof, gy, mode = 'valid')
        xs = x[Nsh:-Nsh]
        #TODO: ensure enough points (>3?)

        #estimate peak position and fwhm width
        peakval, peakpos = pickpeak(profsmooth, 1)

        try:
            halfval, halfpos = pickpeak(
                -numpy.abs(profsmooth - (peakval + numpy.nanmin(profsmooth))/2.0),
                npicks = 2)
            width = numpy.abs(numpy.diff(xs[halfpos]))
        except:
            print "Warning: can't determine initial guess for width", sys.exc_info()
            width = 50

        off = numpy.nanmin(profsmooth) #TODO: can we do better (robust?)
        try:
            m = xs[peakpos]
        except IndexError:
            m = 0.5*(x[0] + x[-1])
            
        s = width
        A = peakval - off

        #make gaussian fit
        startpars = numpy.r_[A, m, s, off]
        
        fitpar = LM.LM(self.fJgauss1d,
                    startpars,
                    args = (x, prof),
                    kmax = 30,
                    eps1 = 1e-6,
                    eps2 = 1e-6,
                    verbose = self.verbose,
                    )

        return fitpar
        

    def do_fit(self,img, roi):
        x = numpy.asarray(roi.xrange_clipped(img), dtype = imgtype)
        y = numpy.asarray(roi.yrange_clipped(img), dtype = imgtype)

        imgroi = img[roi.y, roi.x]
        try:
            imgroifilled = imgroi.filled()
        except AttributeError:
            imgroifilled = imgroi
            
        xprof = imgroi.sum(0)
        yprof = imgroi.sum(1)

        startparx = self._find_startpar_gauss(x,xprof)
        startpary = self._find_startpar_gauss(y,yprof)
        
        startpar = [startparx[0]/(startpary[2]*numpy.sqrt(2*numpy.pi)),
                    startparx[1], #m_x
                    startpary[1], #m_y
                    (startparx[2] + startpary[2])/2, #sigma
                    0 #offset
            ]

        x.shape = (1,-1)
        y.shape = (-1, 1)

        imgsel = numpy.ma.getmaskarray(imgroi.ravel())
        fitpar, J, r = LM.LM(self.fJ_masked,
                             startpar,
                             args = (x, y, imgroi, imgsel),
                             kmax = 30,
                             eps1 = 1e-6,
                             eps2 = 1e-6,
                             verbose = self.verbose,
                             full_output = True,
                             )
                        
        imgfit = self.gauss2d(fitpar, x, y)
        fitparerror, sigma = LM.fitparerror( fitpar, J, r)

        fitpar = fitpar[[0,1,2,3,3,4]]
        fitparerror = fitparerror[[0,1,2,3,3,4]]

        fitpars = FitParsGauss2d(fitpar, self.imaging_pars, fitparerror, sigma)

        #validity check
        A, mx, my, s, offs = fitpar[0:5]
        s = abs(s)
        if A<0:
            fitpars.invalidate()
        if mx < roi.xmin - 100 or mx > roi.xmax + 100:
            fitpars.invalidate()
        if my < roi.ymin - 100 or my > roi.ymax + 100:
            fitpars.invalidate()
        if s > 3*abs(roi.xmax - roi.xmin):
            fitpars.invalidate()

        background = numpy.array([fitpars.offset], dtype = imgtype)
        return [imgfit,], background, fitpars


class Bimodal2d(Gauss2d):
    """Perform fit of 2d bimodal distribution (sum of gaussian and
    inverted parabola) to data.
    @sort: do_fit, bimodal2d, bimodal2d_flat, Dbimodal2d"""

    def __init__(self, imaging_pars = None):
        super(Bimodal2d, self).__init__(imaging_pars)
        self.MyFitPars = FitParsBimodal2d

    def bimodal2d(self, pars, x, y, v0 = 0, full_output = False):
        """calculate 2d bimodal distribution. See L{gauss2d} for
        parameter description.
        
        @param full_output: return gaussian and parabola seperately,
        for L{Dbimodal2d}

        @type full_output: bool
        """
        A, mx, my, sx, sy, offs, B, rx, ry, theta = pars[0:10]

        key = (A, mx, my, sx, sy, B, rx, ry, theta)

        if self.cache.has_key(key):
            [g, b] = self.cache[key]
        else:
            g = A*numpy.exp(- (x-mx)**2 / (2*sx**2) 
                            - (y-my)**2 / (2*sx**2))
            b = B*numpy.exp(-((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))**2/(2.0*rx**2)) - ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))**2/(2.0*ry**2)))
         


        #if full_output:
         #   return [g,b]
        #else:
        return g + b + offs - v0

    def bimodal2d_flat(self, pars, x, y, v0=0):
        return self.bimodal2d(pars, x, y, v0).reshape((-1,))

    def Dbimodal2d(self, pars, x, y, v=0):
        A, mx, my, sx, sy, offs, B, rx, ry, theta = pars[0:10]

        [g, b] = self.bimodal2d(pars, x, y, full_output = True)
        
        J = numpy.empty(shape = (10,) + g.shape, dtype = imgtype)
        J[0] = (1.0/A) * g
        #J[1] = (1.0/sx**2 * g + (3.0*B/(rx**2))) * (x-mx) * b #TODO: wrong?
        J[1] = 1.0/sx**2*g*(x-mx)+(numpy.cos(theta)*(numpy.sin(theta)*y+numpy.cos(theta)*x-my*numpy.sin(theta)-mx*numpy.cos(theta))/rx**2-numpy.sin(theta)*(numpy.cos(theta)*y-numpy.sin(theta)*x+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry**2)*b 
        J[2] = 1.0/sx**2*g*(y-my)+(numpy.sin(theta)*(numpy.sin(theta)*y+numpy.cos(theta)*x-my*numpy.sin(theta)-mx*numpy.cos(theta))/rx**2+numpy.cos(theta)*(numpy.cos(theta)*y-numpy.sin(theta)*x+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry**2)*b 
        J[3] = (1.0/sx**3) * g * ((x-mx)**2)
        J[4] = (1.0/sx**3) * g * ((y-my)**2)
        J[5] = 1
        J[6] = 1.0/B*b
        J[7] = b/rx**3*(numpy.sin(theta)*y+numpy.cos(theta)*x-numpy.sin(theta)*my-numpy.cos(theta)*mx)**2
        J[8] = b/ry**3*(numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)**2
        J[9] = -b*((numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)*(numpy.sin(theta)*y+numpy.cos(theta)*x-numpy.sin(theta)*my-numpy.cos(theta)*mx)/rx**2+(-numpy.sin(theta)*y-numpy.cos(theta)*x+numpy.sin(theta)*my+numpy.cos(theta)*mx)*(numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)/ry**2)
       
        return J.reshape((10, -1))

    def fJ(self, pars, x, y, v0 = 0):
        #print pars
        A, mx, my, sx, sy, offs, B, rx, ry, theta = pars[0:10]

        g = A*numpy.exp(- (x-mx)**2 / (2*sx**2) 
                        - (y-my)**2 / (2*sx**2))
        b = B*numpy.exp(-((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))/(2.0*rx**2)) - ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))/(2.0*ry**2)))

        J = numpy.empty(shape = (10,) + g.shape, dtype = imgtype)
        J[0] = (1.0/A) * g
        #J[1] = (1.0/sx**2 * g + (3.0*B/(rx**2))) * (x-mx) * b #TODO: wrong?
        J[1] = 1.0/sx**2*g*(x-mx)+(numpy.cos(theta)*(numpy.sin(theta)*y+numpy.cos(theta)*x-my*numpy.sin(theta)-mx*numpy.cos(theta))/rx**2-numpy.sin(theta)*(numpy.cos(theta)*y-numpy.sin(theta)*x+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry**2)*b 
        J[2] = 1.0/sx**2*g*(y-my)+(numpy.sin(theta)*(numpy.sin(theta)*y+numpy.cos(theta)*x-my*numpy.sin(theta)-mx*numpy.cos(theta))/rx**2+numpy.cos(theta)*(numpy.cos(theta)*y-numpy.sin(theta)*x+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry**2)*b 
        J[3] = (1.0/sx**3) * g * ((x-mx)**2)
        J[4] = (1.0/sx**3) * g * ((y-my)**2)
        J[5] = 1
        J[6] = 1.0/B*b
        J[7] = b/rx**3*(numpy.sin(theta)*y+numpy.cos(theta)*x-numpy.sin(theta)*my-numpy.cos(theta)*mx)**2
        J[8] = b/ry**3*(numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)**2
        J[9] = -b*((numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)*(numpy.sin(theta)*y+numpy.cos(theta)*x-numpy.sin(theta)*my-numpy.cos(theta)*mx)/rx**2+(-numpy.sin(theta)*y-numpy.cos(theta)*x+numpy.sin(theta)*my+numpy.cos(theta)*mx)*(numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)/ry**2)
             
        f = g + b + offs - v0
        f.shape = (-1,)
        J.shape = (10,-1)
        return f, J

    def rF(self, pars, x, y):
        """
        calculate seperately nonlinear functions and the derivatives (reduced problem)
        """
        
        mx, my, sx, sy, rx, ry, theta = pars

        X,Y = numpy.broadcast_arrays(x,y)
        F = numpy.empty(shape = (3,) + X.shape)

        #gauss
        numpy.multiply(numpy.exp( -(x-mx)**2/(2*sx**2)),
                       numpy.exp( -(y-my)**2/(2*sx**2)),
                       F[0])

        #TF
        numpy.multiply(numpy.exp(-((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))**2/(2.0*rx**2))),
                       numpy.exp(-((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))**2/(2.0*ry**2))),
                       F[1])
        #offset
        F[2] = 1

        #derivatives
        Fd = []
        #mx
        Fdmx = numpy.empty_like(F)
        
        numpy.multiply(F[0], 1.0/(sx**2)*(x-mx), Fdmx[0])
        numpy.multiply(F[1],(numpy.cos(theta)*(numpy.sin(theta)*y+numpy.cos(theta)*x-my*numpy.sin(theta)-mx*numpy.cos(theta))/rx**2-numpy.sin(theta)*(numpy.cos(theta)*y-numpy.sin(theta)*x+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry**2), Fdmx[1])
        Fdmx[2] = 0

        #my
        Fdmy = numpy.empty_like(F)
        numpy.multiply(F[0], 1.0/(sx**2)*(y-my), Fdmy[0])
        numpy.multiply(F[1], (numpy.sin(theta)*(numpy.sin(theta)*y+numpy.cos(theta)*x-my*numpy.sin(theta)-mx*numpy.cos(theta))/rx**2+numpy.cos(theta)*(numpy.cos(theta)*y-numpy.sin(theta)*x+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry**2), Fdmy[1])
        Fdmy[2] = 0

        #sx
        Fdsx = numpy.empty_like(F)
        numpy.multiply(F[0], 1.0/sx**3 * ((x-mx)**2), Fdsx[0])
        Fdsx[1] = 0
        Fdsx[2] = 0

        #sy
        Fdsy = numpy.empty_like(F)
        numpy.multiply(F[0], 1.0/sx**3 * ((y-my)**2), Fdsy[0])
        Fdsy[1] = 0
        Fdsy[2] = 0

        #rx
        Fdrx = numpy.empty_like(F)
        Fdrx[0] = 0
        numpy.multiply(F[1],1.0/rx**3*(numpy.sin(theta)*y+numpy.cos(theta)*x-numpy.sin(theta)*my-numpy.cos(theta)*mx)**2 , Fdrx[1])
        Fdrx[2] = 0

        #ry
        Fdry = numpy.empty_like(F)
        Fdry[0] = 0
        numpy.multiply(F[1],1.0/ry**3*(numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)**2, Fdry[1])
        Fdry[2] = 0
        
        #theta
        Fdtheta = numpy.empty_like(F)
        Fdtheta[0] = 0
        numpy.multiply(F[1], -((numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)*(numpy.sin(theta)*y+numpy.cos(theta)*x-numpy.sin(theta)*my-numpy.cos(theta)*mx)/rx**2+(-numpy.sin(theta)*y-numpy.cos(theta)*x+numpy.sin(theta)*my+numpy.cos(theta)*mx)*(numpy.cos(theta)*y-numpy.sin(theta)*x+numpy.sin(theta)*mx-numpy.cos(theta)*my)/ry**2), Fdtheta[1])
        Fdtheta[2] = 0
        
        
        #finish

        Fd = [Fdmx, Fdmy, Fdsx, Fdsy, Fdrx, Fdry, Fdtheta]
        nz = [slice(0,2), slice(0,2), slice(0,1), slice(0,1), slice(1,2), slice(1,2), slice(1,2)] #non zero pages of Fd[i] 

        F.shape = (F.shape[0], -1)

        for A in Fd:
            A.shape = (A.shape[0], -1)

        return F, Fd, nz

    def fJr(self, pars, x, y, vin = 0, sel = None, calcJ = True):
        """
        calculate f and J for reduced system (only nonlinear parameters)
        """

        F, Fd, nz = self.rF(pars, x, y)

        #F[2] = 0 # fit with zero offset

        v = numpy.ravel(vin)

        #calculate linear Parameters
        FtF = numpy.inner(F, F)
        Fty = numpy.inner(F, v)
        try:
            c = numpy.linalg.solve(FtF, Fty)
        except numpy.linalg.LinAlgError:
            print "normal equations numpy.singular, retrying"
            c, res, rank, s = numpy.linalg.lstsq(F.transpose(),v)

        #magic: if gauss or bec amplitude negative: force it to zero
        if c[1] < 0:
            cm, res, rank, s = numpy.linalg.lstsq(F[[0,2]].transpose(), v)
            c = numpy.array([cm[0], 0.0, cm[1]])

        if c[0] < 0:
            cm, res, rank, s = numpy.linalg.lstsq(F[[1,2]].transpose(), v)
            c = numpy.array([0.0, cm[0], cm[1]])
            
        #calculate residuum
        r = numpy.dot(c, F) - v

        if not calcJ:
            return r, c, F

        ##calculate complete Jacobian
        cd = numpy.empty(shape = (len(pars),) + c.shape)
        Jr = numpy.empty(shape = (len(pars),) + F.shape[1:])

        for j in range(len(pars)):
            cFdj = numpy.dot(c[nz[j]], Fd[j][nz[j]])

            #rm = numpy.inner(Fd[j], r) - numpy.inner(F, cFdj) #expensive
            rm = numpy.zeros(shape = Fd[j].shape[0])
            rmnz = numpy.inner(Fd[j][nz[j]], r)
            rm[nz[j]] = rmnz
            rm -= numpy.inner(F, cFdj) #expensive
            try:
                cd[j] = numpy.linalg.solve(FtF, rm) #cheap
            except numpy.linalg.LinAlgError:
                print "numpy.singular matrix in complete Jacobian, retrying"
                cdj, res, rank, s = numpy.linalg.lstsq(F.transpose(), cFdj)
                cd[j] = -cdj
                
            Jr[j] = cFdj + numpy.dot(cd[j], F) #expensive!

        #tic2 = time()
        #print "%.2f"%(1e3*(time()-tic2))

        if sel is None:
            sel = numpy.ma.getmaskarray(v)
        r[sel] = 0
        Jr[:,sel] = 0

        return r, Jr

    def do_fit(self, img, roi):
        """
        @rtype: [fit image, fit image gauss only], fit background, FitPars
        """
        x = numpy.asarray(roi.xrange_clipped(img), dtype = imgtype)
        y = numpy.asarray(roi.yrange_clipped(img), dtype = imgtype)

        imgroi = img[roi.y, roi.x]
        imgroifilled = imgroi.filled()

        xprof = imgroifilled.sum(0)
        yprof = imgroifilled.sum(1)

        startparx = self._find_startpar_gauss(x,xprof)
        startpary = self._find_startpar_gauss(y,yprof)

        [Ax, mx, sx, ox] = startparx[0:4]
        [Ay, my, sy, oy] = startpary[0:4]
        A = Ay/(numpy.sqrt(2*numpy.pi)*sx)
        sx = (sx + sy)/2.0
        sy = sx
        # Case A: large thermal, small BEC
        startparA = numpy.array([A*0.5,
                                mx,
                                my,
                                sx ,
                                sx ,
                                0.5*(ox/len(y)+oy/len(x)),
                                A*0.5,
                                sx ,
                                sx/2,
                                numpy.pi/8.]
                               )

        # Case B: small thermal, large BEC
        startparB = numpy.array([A,
                                mx,
                                my,
                                sx ,
                                sx,
                                0.5*(ox/len(y)+oy/len(x)),
                                A*0.2,
                                sx/0.5 ,
                                sx/2.0,
                                numpy.pi/8.]
                               )

        if self.verbose:
            print "gauss fit profile horz: A = %3.1f, sx = %3.1f, offset %4.1f"%(A, sx, ox)
            print "gauss fit profile vert: A = %3.1f, sx = %3.1f, offset %4.1f"%(A, sx, ox)
        
        x.shape = (1,-1)
        y.shape = (-1, 1)
        startpar = startparB
        if use_minpack:
            fitpar, cov, infodict, mesg, ier = \
                    leastsq(self.bimodal2d_flat,
                            startpar,
                            args = (x,y,imgroi),
                            Dfun = self.Dbimodal2d, col_deriv=1,
                            maxfev = 5000,
                            ftol = 1e-10,
                            full_output = 1,
                            )
        else:
            usereduced = True

            if usereduced:
                imgsel = numpy.ma.getmaskarray(imgroi.ravel())

                ##selection of startpars
                rA,cA,FA = self.fJr(startparA[[1,2,3,4,7,8,9]], x,y,imgroi,imgsel, calcJ=False)
                rB,cB,FB = self.fJr(startparB[[1,2,3,4,7,8,9]], x,y,imgroi,imgsel, calcJ=False)
                rA = abs(rA**2).sum()
                rB = abs(rB**2).sum()
                print "A: small BEC:", cA, rA
                print "B: large BEC:", cB, rB
                if rA<rB:
                    print "I guess: small BEC"
                    startparlist = [startparA, startparB]
                else:
                    print "I guess: large BEC"
                    startparlist = [startparB, startparA]

                for startpar in startparlist:
                    startpar_red = startpar[ [1,2,3,4,7,8,9] ]
                    p, J, f = LM.LM(self.fJr,
                           startpar_red,
                           args = (x,y,imgroi,imgsel),
                           #args = (x[::3,::3], y[::3,::3], 
                                    #imgroi[::3, ::3], 
                                    #numpy.ma.getmaskarray(imgroi[::3, ::3].ravel())),
                           kmax = 1000,
                           eps1 = 1e-7,
                           eps2 = 2e-7,
                           tau = 1e-4,
                           verbose = self.verbose,
                           full_output = True)
                    #TODO: check for fit succeed

                    r,c,F = self.fJr(p,x,y,imgroi, calcJ = False)
                    fitpar = numpy.array([c[0], p[0], p[1], p[2], p[3], 
                                          c[2], c[1], p[4], p[5], p[6]])

                    Jfull = numpy.vstack((F, J))
                    cepe, sigma = LM.fitparerror( numpy.hstack((c, p)), Jfull, r)
                    ce, pe = cepe[:3], cepe[3:]
                    fitparerr = numpy.array([ce[0], pe[0], pe[1], pe[2], pe[3], 
                                             ce[2], ce[1], pe[4], pe[5]])

                    #pe = LM.fitparerror(p,J,f)
                    print 'fitpars', fitpar
                    #print 'fitparerr', pe
                    #fitparerr = numpy.array([0.0, pe[0], pe[1], pe[2], pe[3], 0.0, 0.0, pe[4], pe[5]])
                    if c[0]>0 and c[1]>0:
                        #both thermal and BEC fraction are nonzero
                        print "fit converged"
                        break
                    else:
                        print "fit possibly didn't converge, can we retry?"
                else:
                    print "fit didn't converge!"
                    #TODO: FitNoFit
                    
            else:
                #TODO: also implement two different starting pars!!!!!!
            
                imgsel = numpy.ma.getmaskarray(imgroi.ravel())
                
                fitpar, J, r = LM.LM(self.fJ_masked,
                                    startparA,
                                    args = (x, y, imgroi, imgsel),
                                    kmax = 3000,
                                    eps1 = 1e-8,
                                    eps2 = 1e-8,
                                    verbose = self.verbose,
                                    full_output = True,
                                    )
                                    
                fitparerr, sigma = LM.fitparerror(fitpar, J, r)
          
        imgfit = self.bimodal2d(fitpar, x, y)
        print 'yuhu'        
        print fitpar 
        fitpargaussonly = fitpar.copy() # make copy
        fitpargaussonly[6] = 0
        imgfitgaussonly = self.bimodal2d(fitpargaussonly, x, y)
         
        
        fitpars = self.MyFitPars(fitpar, self.imaging_pars, fitparerr, sigma)
               
        background = numpy.array([fitpars.offset], dtype = imgtype)
        
        return [imgfit, imgfitgaussonly], background, fitpars


def g2(x, out=None):
    """bose function"""
    if out is None:
        return scipy.special.spence(1.0-x)
    else:
        return scipy.special.spence(1.0-x, out)

def dg2(x, out=None):
    """derivative of g2(x)"""
    #y = -log(1-x)/x
    if out is None:
        y = numpy.subtract(1.0, x)
    else:
        numpy.subtract(1.0,x,out)
        y = out
    numpy.log(y,y)
    numpy.divide(y,x,y)
    numpy.negative(y,y)
    
    y[x<=0.0] = 1.0
    y[x==1.0] = 0.0
    if numpy.any(~numpy.isfinite(y)):
        print "some non finite entries in dg2!"
    
    return y
    
class BoseBimodal2d(Bimodal2d):
    """Perform fit of 2d bimodal distribution (sum of bose enhanced gaussian
    and inverted parabola) to data.  
    
    @sort: do_fit, bimodal2d, bimodal2d_flat, Dbimodal2d"""

    def __init__(self, imaging_pars = None):
        super(BoseBimodal2d, self).__init__(imaging_pars)
        self.MyFitPars = FitParsBoseBimodal2d


    def bimodal2d(self, pars, x, y, v0 = 0, full_output = False):
        """calculate 2d bose enhanced bimodal distribution. See L{gauss2d} for
        parameter description.
        
        @param full_output: return bose enhanced gaussian and parabola
        seperately, for L{Dbimodal2d}

        @type full_output: bool
        """

        A, mx, my, sx, sy, offs, B, rx, ry, theta = pars[0:10]

        key = (A, mx, my, sx, sy, B, rx, ry, theta)
        
        if self.cache.has_key(key):
            [g, b] = self.cache[key]
        else:
            g = numpy.exp(- (x-mx)**2 / (2*sx**2) 
                            - (y-my)**2 / (2*sx**2))
            g2(g,g)
            numpy.multiply(g, A, g)
            b = (1 - ((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))/rx)**2 - ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry)**2)
            numpy.maximum(b, 0, b)
            numpy.sqrt(b,b)

        if full_output:
            return [g,b]
        else:
            return g + B*(b**3) + offs - v0

    def bimodal2d_flat(self, pars, x, y, v0=0):
        return self.bimodal2d(pars, x, y, v0).reshape((-1,))

    def rF(self, pars, x, y):
        """
        calculate seperately nonlinear functions and the derivatives (reduced problem)
        """
        
        mx, my, sx, sy, rx, ry, theta = pars

        X,Y = numpy.broadcast_arrays(x,y)
        F = numpy.empty(shape = (3,) + X.shape)

        #gauss
        numpy.multiply(numpy.exp( -(x-mx)**2/(2*sx**2)),
                       numpy.exp( -(y-my)**2/(2*sx**2)),
                       F[0])

        #TF
        b = F[1]
        numpy.maximum((1 - ((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))/rx)**2 - ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry)**2), 0, b)
        numpy.sqrt(b,b)
        #numpy.power(b,3,b)

        #offset
        F[2] = 1

        #derivatives
        Fd = []
        #mx
        Fdmx = numpy.empty_like(F)
        
        numpy.multiply(F[0], 1.0/(sx**2)*(x-mx), Fdmx[0])
        numpy.multiply(F[1], 3.0/(rx**2)*((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))*numpy.cos(theta))/rx**2- ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))*numpy.sin(theta)), Fdmx[1])
        Fdmx[2] = 0

        #my
        Fdmy = numpy.empty_like(F)
        numpy.multiply(F[0], 1.0/(sx**2)*(y-my), Fdmy[0])
        numpy.multiply(F[1], 3.0/(ry**2)*((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))*numpy.sin(theta))/rx**2+ ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))*numpy.cos(theta)), Fdmy[1])
        Fdmy[2] = 0

        #sx
        Fdsx = numpy.empty_like(F)
        numpy.multiply(F[0], 1.0/sx**3 * ((x-mx)**2), Fdsx[0])
        Fdsx[1] = 0
        Fdsx[2] = 0

        #sx
        Fdsy = numpy.empty_like(F)
        numpy.multiply(F[0], 1.0/sx**3 * ((y-my)**2), Fdsy[0])
        Fdsy[1] = 0
        Fdsy[2] = 0

        #rx
        Fdrx = numpy.empty_like(F)
        Fdrx[0] = 0
        numpy.multiply(F[1], 3.0/(rx**3) *(x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))**2 , Fdrx[1])
        Fdrx[2] = 0

        #ry
        Fdry = numpy.empty_like(F)
        Fdry[0] = 0
        numpy.multiply(F[1], 3.0/(ry**3) *  (-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))**2, Fdry[1])
        Fdry[2] = 0
        
        #theta
        Fdtheta = numpy.empty_like(F)
        Fdtheta[0] = 0
        numpy.multiply(F[1], - 3.0*((((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta)))*(-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta)))/rx**2+(((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta)))*(-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta)))/ry**2), Fdtheta[1])
        Fdtheta[2] = 0
        
        
        #finish
        numpy.power(b,3,b)
        
        Fd = [Fdmx, Fdmy, Fdsx, Fdsy, Fdrx, Fdry, Fdtheta]
        nz = [slice(0,2), slice(0,2), slice(0,1), slice(0,1), slice(1,2), slice(1,2), slice(1,2)] #non zero pages of Fd[i] 

        F.shape = (F.shape[0], -1)

        for A in Fd:
            A.shape = (A.shape[0], -1)

        return F, Fd, nz

class ThomasFermi2d(Gauss2d):
    """Perform fit of 2d Thomas=Fermi distribution to data.
    @sort: do_fit, TF2d, TF2d_flat, DTF2d, fJ"""

    def TF2d(self, pars, x, y, v0 = 0, full_output = False):
        """calculate Thomas-Fermi 2d distribution. See L{gauss2d} for
        parameter description.
        
        @param full_output: return only Thomas (no background)
        for L{TF2d}

        @type full_output: bool
        """
        mx, my, offs, B, rx, ry, theta = pars[0:7]

        key = (mx, my, B, rx, ry, theta)

        if self.cache.has_key(key):
            b = self.cache[key]
        else:
            b = (1 - ((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))/rx)**2 - ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry)**2)
            numpy.maximum(b, 0, b)
            numpy.sqrt(b,b)

        if full_output:
            return b
        else:
            return B*(b**3) + offs - v0

    def TF2d_flat(self, pars, x, y, v0=0):
        return self.TF2d(pars, x, y, v0).reshape((-1,))

    def DTF2d(self, pars, x, y, v=0):
        mx, my, offs, B, rx, ry = pars[0:6]

        b = self.TF2d(pars, x, y, full_output = True)
        
        J = numpy.empty(shape = (6,)+ b.shape, dtype = imgtype)

        J[0] = ((3.0*B/(rx**2))) * (x-mx) * b 
        J[1] = ((3.0*B/(ry**2))) * (y-my) * b
        J[2] = 1
        J[3] = b**3
        J[4] = (3.0*B/(rx**3)) * ((x-mx)**2) * b
        J[5] = (3.0*B/(ry**3)) * ((y-my)**2) * b

        return J.reshape((6, -1))

    def fJ(self, pars, x, y, v0 = 0):
        mx, my, offs, B, rx, ry, theta = pars[0:7]
        
        b = (1 - ((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))/rx)**2 - ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))/ry)**2)
        numpy.maximum(b, 0, b)
        numpy.sqrt(b,b)

        J = numpy.empty(shape = (7,) + b.shape, dtype = imgtype)
        
        J[0] = 3.0* B * b *(((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))*numpy.cos(theta))/rx**2- ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))*numpy.sin(theta))/ry**2)
        J[1] = 3.0* B * b *(((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))*numpy.sin(theta))/rx**2+ ((-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))*numpy.cos(theta))/ry**2)
        J[2] = 1
        J[3] = b**3
        J[4] = (3.0*B/(rx**3)) * (x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta))**2  * b
        J[5] = (3.0*B/(ry**3)) * (-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta))**2 * b
        J[6] = - 3.0*B*b*((((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta)))*(-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta)))/rx**2+(((x*numpy.cos(theta)+y*numpy.sin(theta)-mx*numpy.cos(theta)-my*numpy.sin(theta)))*(-x*numpy.sin(theta)+y*numpy.cos(theta)+mx*numpy.sin(theta)-my*numpy.cos(theta)))/ry**2)

        f = B*(b**3) + offs - v0
        f.shape = (-1,)
        J.shape = (7,-1)
        return f, J

    def do_fit(self, img, roi):
        """
        @rtype: [fit image, fit image gauss only], fit background, FitPars
        """
        x = numpy.asarray(roi.xrange_clipped(img), dtype = imgtype)
        y = numpy.asarray(roi.yrange_clipped(img), dtype = imgtype)

        imgroi = img[roi.y, roi.x]
        imgroifilled = imgroi.filled()

        xprof = imgroifilled.sum(0)
        yprof = imgroifilled.sum(1)

        startparx = self._find_startpar_gauss(x,xprof)
        startpary = self._find_startpar_gauss(y,yprof)

        [Ax, mx, sx, ox] = startparx[0:4]
        [Ay, my, sy, oy] = startpary[0:4]
        A = Ay/(numpy.sqrt(2*numpy.pi)*sx)

        startpar = [mx,
                    my,
                    0.5*(ox/len(y)+oy/len(x)),
                    A*0.8,
                    sx*0.5,
                    sy*0.5,
                    numpy.pi/4.]

        x.shape = (1,-1)
        y.shape = (-1, 1)

        if use_minpack:
            fitpar, cov, infodict, mesg, ier = \
                    leastsq(self.TF2d_flat,
                            startpar,
                            args = (x,y,imgroi),
                            Dfun = self.DTF2d, col_deriv=1,
                            maxfev = 50,
                            ftol = 1e-6,
                            full_output = 1,
                            )
        else:
            imgsel = numpy.ma.getmaskarray(imgroi.ravel())
            fitpar, J, r = LM.LM(self.fJ_masked,
                                 startpar,
                                 args = (x, y, imgroi, imgsel),
                                 kmax = 30,
                                 eps1 = 1e-6,
                                 eps2 = 1e-6,
                                 verbose = self.verbose,
                                 full_output = True,
                                 )
        fitparerr, sigma = LM.fitparerror(fitpar, J, r)
        imgfit = self.TF2d(fitpar, x, y)
        
        fitpars = FitParsTF2d(fitpar, self.imaging_pars, fitparerr, sigma)
        background = numpy.array([fitpars.offset], dtype = imgtype)
        
        return [imgfit,], background, fitpars


class FitPars(object):
    """base class for representing fit results. Never used directly.
    @ivar valid: indicates that fit parameters are valid
    @cvar fitparnames: list of fit parameter names
    @cvar fitparunits: list of fit parameter unit names
    """

    valid = True
    fitparnames = []
    fitparunits = []

    def __str__(self):
        """give nice printable representation of fit parameters"""
        pass
    
    def valuedict(self):
        """@return: dictionary of fit parameters
        @rtype: dict"""
        
        result = dict()
        for key in self.fitparnames:
            result[key] = self.__getattribute__(key)
            
        result['params'] = "%s, %s"%(self.description, str(self.imaging_pars))
        return result

    def invalidate(self):
        self.valid = False
        
class FitParsNoFit(FitPars):
    """Result if L{NoFit} has been performed. Always invalid."""
    description = "no fit"
    imaging_pars = None
    valid = False

    def __init__(self):
        FitPars.__init__(self)
        
    def __str__(self):
        return "no fit"
     

######Original FitPars Gauss class#################

class FitParsGauss2d(FitPars):
    """
    Class for storing results of fit of 2d gaussian to data.

    """
    description = "Gauss2d"
    fitparnames = ['OD', 'ODerr',
                   'sx', 'sxerr', 
                   'sy', 'syerr', 
                   'mx', 'mxerr', 
                   'my', 'myerr', 
                   'T', 
                   'N', 'Nerr', 
                   'sigma'
                   ]
    fitparunits = ['', ''
                   '�m', '�m', '�m', '�m', 
                   'px', 'px', 'px', 'px', 
                   '�K', 
                   'K', 'K',
                   '',
                   ]
    
    def __init__(self, fitpars, imaging_pars, fitparerr = numpy.zeros(6), sigma = 0.0, Counts = 0.0):
        """
        Initialize.

        @param fitpars: fit parameter as used internally in L{Gauss2d}
        
        @param imaging_pars: imaging pars, needed for calculation of
        atom number, cloud size, ...
        @type imaging_pars: L{ImagingPars}
        """
        
        (self.A, 
         self.mx,
         self.my,
         self.sxpx,
         self.sypx,
         self.offset) = fitpars[0:6]

        (self.Aerr,
         self.mxerr,
         self.myerr,
         self.sxpxerr,
         self.sypxerr,
         self.offseterr) = fitparerr[0:6]
         
        self.Counts = Counts
        self.sigma = sigma
        self.valid = True
        self.imaging_pars = imaging_pars

    @property
    def N(self):
        "atom number in thousand"
        
        N = 1e-3 * 2*numpy.pi * \
            (self.A/100.) * self.sx*1e-6 * self.sy*1e-6 / self.imaging_pars.sigma0 #this is for absorption, the 45 comes from a factor in Acquire for contrast (line 364)
        # uncomment this for fluorescence 
        '''
        N = 1e-3*self.Counts*8*numpy.pi* (1+4*self.imaging_pars.detuning**2 +6*self.imaging_pars.I_red)/ \
                (self.imaging_pars.dO*self.imaging_pars.qe*self.imaging_pars.t_exp* \
                self.imaging_pars.gamma*6*self.imaging_pars.I_red)
        
        result = 1e-3*numpy.pi*2.*self.A*self.sxpx*self.sypx * \
                8*numpy.pi* (1+4*self.imaging_pars.detuning**2 +6*self.imaging_pars.I_red)/ \
                (self.imaging_pars.dO*self.imaging_pars.qe*self.imaging_pars.t_exp* \
                self.imaging_pars.gamma*6*self.imaging_pars.I_red)
        N = abs(result)
        '''
        return N

    @property
    def Nerr(self):
        "error atom number"
        Nerr = 1e-3 * 2*numpy.pi / self.imaging_pars.sigma0 * 1e-12 *\
               numpy.sqrt( (self.Aerr*self.sx*self.sy)**2 +
                           (self.A*self.sxerr*self.sy)**2 +
                           (self.A*self.sx*self.syerr)**2 )
        return Nerr

    @property
    def OD(self):
        "optical density"
        return self.A/5.0
        #45 comes from a factor in Acquire for contrast (line 364)
        # uncomment this for fluorescence 

    @property
    def ODerr(self):
        "error optical density"
        return self.Aerr

    @property
    def sx(self):
        "width of gaussian in �m"
        return abs(self.sxpx) * self.imaging_pars.pixelsize

    @property
    def sy(self):
        "width of gaussian in �m"
        return abs(self.sypx) * self.imaging_pars.pixelsize

    @property
    def sxerr(self):
        "error width of gaussian in �m"
        return abs(self.sxpxerr) * self.imaging_pars.pixelsize

    @property
    def syerr(self):
        "error width of gaussian in �m"
        return abs(self.sypxerr) * self.imaging_pars.pixelsize
    
    @property
    def T(self):
        "temperature of cloud in �K"
        if self.imaging_pars.expansion_time:
            return (self.sx*1e-6)**2 / \
                   (self.imaging_pars.expansion_time*1e-3)**2 * \
                   self.imaging_pars.mass / 1.38e-23 * 1e6
        else:
            return 0.0

    @property
    def Terr(self):
        if self.imaging_pars.expansion_time:
            return numpy.sqrt( (self.sx*self.syerr)**2 + (self.sxerr*self.sy)**2 ) / \
                   (self.imaging_pars.expansion_time*1e-3)**2 * \
                   self.imaging_pars.mass / 1.38e-23 * 1e6 * 1e-12
        else:
            return 0.0
        
    def __str__(self):
        s = u"OD: %6.2f\n" \
            u"     �%3.2f\n"  \
            u"mx: %5.1f px\n" \
            u"     �%3.2f\n" \
            u"my: %5.1f px\n" \
            u"     �%3.2f\n"  \
            u"sx: %5.1f �m\n" \
            u"     �%3.2f\n" \
            u"sy: %5.1f �m\n" \
            u"     �%3.2f\n" \
            u"T : %5.3f �K\n" \
            u"   �%5.3f\n" \
            u"N : %5.1f k\n" \
            u"    �%3.2f" \
            %(self.OD, self.ODerr,
              self.mx, self.mxerr,
              self.my, self.myerr,
              self.sx, self.sxerr,
              self.sy, self.syerr,
              self.T, self.Terr,
              self.N, self.Nerr)
        return s
        
######################End of original fitpars Gauss#####################



###############duplicate of fitpars gauss for fluorescence###############        
class FitParsFluorescenceGauss(FitPars):
    """
    Class for storing results of fit of 2d gaussian to data.

    """
    description = "FluorescenceGauss"
    fitparnames = ['OD', 'ODerr','OD2','OD2err',
                   'N','Nerr','N2','N2err',
                   'sx','sxerr','sy','syerr',
                   'sx2','sx2err','sy2','sy2err',
                   'T'
                   ]
                   
    fitparunits = ['', '','','',
                   'k','k','k','k'
                   '�m','�m','�m','�m',
                   '�m','�m','�m','�m',
                   '�K',
                   ]
    
    def __init__(self, fitpars, imaging_pars, fitparerr = numpy.zeros(11), sigma = 0.0, Counts = 0.0):
        """
        Initialize.

        @param fitpars: fit parameter as used internally in L{Gauss2d}
        
        @param imaging_pars: imaging pars, needed for calculation of
        atom number, cloud size, ...
        @type imaging_pars: L{ImagingPars}
        """
        self.sigma = sigma
        self.valid=True
        self.imaging_pars=imaging_pars
        
        (self.A1, 
         self.A2,
         self.m1x,
         self.m2x,
         self.m1y,
         self.m2y,
         self.sxpx1,
         self.sxpx2,
         self.sypx1,
         self.sypx2,
         self.offset) = fitpars[0:11]

        (self.A1err,
         self.A2err,
         self.m1xerr,
         self.m2xerr,
         self.m1yerr,
         self.m2yerr,
         self.sxpx1err,
         self.sxpx2err,
         self.sypx1err,
         self.sypx2err,
         self.offseterr) = fitparerr[0:11]
         
        self.Counts = Counts
        self.sigma = sigma
        self.valid = True
        self.imaging_pars = imaging_pars
        
        

    @property
    def OD(self):
        "optical density"
        return self.A1/5.

    @property
    def ODerr(self):
        "error optical density"
        return self.A1err
    
    @property
    def OD2(self):
        "optical density"
        return self.A2/5.
        
    @property
    def OD2err(self):
        "error optical density"
        return self.A2err
    
    @property
    def sx(self):
        "width of gaussian in �m"
        return abs(self.sxpx1) * self.imaging_pars.pixelsize

    @property
    def sy(self):
        "width of gaussian in �m"
        return abs(self.sypx1) * self.imaging_pars.pixelsize
    
    @property
    def sxerr(self):
        "error width of gaussian in �m"
        return abs(self.sxpx1err) * self.imaging_pars.pixelsize

    @property
    def syerr(self):
        "error width of gaussian in �m"
        return abs(self.sypx1err) * self.imaging_pars.pixelsize
    
    @property
    def N(self):
        "atom number in thousand"
        N = 1e-3 * 2*numpy.pi * \
            (self.A1/5.) * self.sx*1e-6 * self.sy*1e-6 / self.imaging_pars.sigma0
        return N
    @property
    def Nerr(self):
        "error atom number"
        Nerr = 1e-3 * 2*numpy.pi / self.imaging_pars.sigma0 * 1e-12 *\
               numpy.sqrt( (self.A1err*self.sx*self.sy)**2 +
                           (self.A1*self.sxerr*self.sy)**2 +
                           (self.A1*self.sx*self.syerr)**2 )
        return Nerr
    
    @property
    def sx2(self):
        "width of gaussian in �m"
        return abs(self.sxpx2) * self.imaging_pars.pixelsize

    @property
    def sy2(self):
        "width of gaussian in �m"
        return abs(self.sypx2) * self.imaging_pars.pixelsize
    
    @property
    def sx2err(self):
        "error width of gaussian in �m"
        return abs(self.sxpx2err) * self.imaging_pars.pixelsize

    @property
    def sy2err(self):
        "error width of gaussian in �m"
        return abs(self.sypx2err) * self.imaging_pars.pixelsize
    
    @property
    def N2(self):
        "atom number in thousand"
        N2 = 1e-3 * 2*numpy.pi * \
            (self.A2/5.) * self.sx2*1e-6 * self.sy2*1e-6 / self.imaging_pars.sigma0
        return N2
        
    @property
    def N2err(self):
        "error atom number"
        N2err = 1e-3 * 2*numpy.pi / self.imaging_pars.sigma0 * 1e-12 *\
               numpy.sqrt( (self.A2err*self.sx*self.sy)**2 +
                           (self.A2*self.sxerr*self.sy)**2 +
                           (self.A2*self.sx*self.syerr)**2 )
        return N2err
    @property
    def T(self):
        "temperature of cloud in �K"
        if self.imaging_pars.expansion_time:
            return (0.5*((self.sx*1e-6) + (self.sy*1e-6)))**2 / \
                   (self.imaging_pars.expansion_time*1e-3)**2 * \
                   self.imaging_pars.mass / 1.38e-23 * 1e6
        else:
            return 0.0

    @property
    def Terr(self):
        if self.imaging_pars.expansion_time:
            return numpy.sqrt( (self.sx*self.syerr)**2 + (self.sxerr*self.sy)**2 ) / \
                   (self.imaging_pars.expansion_time*1e-3)**2 * \
                   self.imaging_pars.mass / 1.38e-23 * 1e6 * 1e-12
        else:
            return 0.0
            
    def __str__(self):
        s = u"OD: %6.2f\n" \
            u"     �%3.2f\n"  \
            u"OD2: %6.2f\n" \
            u"     �%3.2f\n"  \
            u"N : %5.1f k\n" \
            u"     �%3.2f\n"  \
            u"N2 : %5.1f k\n" \
            u"     �%3.2f\n"  \
            u"sx : %5.1f k\n" \
            u"     �%3.2f\n"  \
            u"sy : %5.1f k\n" \
            u"     �%3.2f\n"  \
            u"sx2 : %5.1f k\n" \
            u"     �%3.2f\n"  \
            u"sy2 : %5.1f k\n" \
            u"     �%3.2f\n"  \
            u"T : %5.1f k\n" \
            u"     �%3.2f\n"  \
            %(self.OD, self.ODerr,
              self.OD2, self.OD2err,
              self.N, self.Nerr,
              self.N2, self.N2err,
              self.sx, self.sxerr,
              self.sy, self.syerr,
              self.sx2, self.sx2err,
              self.sy2, self.sy2err,
              self.T, self.Terr
              )
        return s

#####################End of duplicate gauss fitpars############################
#        
#class FitParsGaussBose2d(FitParsGauss2d):
#    """
#    Class for storing results of fit of 2d bose enhanced gaussian to data.
#    """
#    description = "GaussBose2d"
#
#    def __init__(self, fitpars, imaging_pars, fitparerr = numpy.zeros(6), sigma = 0.0):
#        FitParsGauss2d.__init__(self, fitpars, imaging_pars, fitparerr, sigma)
#
#    @property
#    def N(self):
#        "number of atoms in thermal cloud"
#        Nth = 1e-3 * 0.5*4.885*numpy.pi * \
#              self.A * self.sx*1e-6 * self.sy*1e-6 / self.imaging_pars.sigma0 
#        return Nth
#
#    @property
#    def Nerr(self):
#        "error atom number"
#        Nerr = 1e-3 * 0.5*4.885*numpy.pi / self.imaging_pars.sigma0 * 1e-12 *\
#               numpy.sqrt( (self.Aerr*self.sx*self.sy)**2 +
#                           (self.A*self.sxerr*self.sy)**2 +
#                           (self.A*self.sx*self.syerr)**2 )
#        return Nerr
#
#    @property
#    def OD(self):
#        "optical density"
#        return self.A*g2(1.0)
#
#    @property
#    def ODerr(self):
#        "error optical density"
#        return self.Aerr*g2(1.0)



class FitParsBimodal2d(FitParsGauss2d):
    "Class for storing results of fit of 2d bimodal distribution to data"

    description = "bimodal2d"

    fitparnames = ['sx', 'sxerr', 
                   'sy', 'syerr', 
                   'mx', 'mxerr', 
                   'my', 'myerr', 
                   'rx', 'rxerr', 
                   'ry', 'ryerr', 
                   'N', 'Nth', 'Nbec', 
                   'T',
                   'OD',
                   'sigma','Angle']

    fitparunits = ['�m', '�m', '�m', '�m', 
                   'px', 'px', 'px', 'px',
                   '�m', '�m', '�m', '�m', 
                   '10^3', '10^3', '10^3',
                   '�K',
                   '',
                   '','']

    def __init__(self, fitpars, imaging_pars, fitparerr = numpy.zeros(10), sigma = 0.0):
        FitParsGauss2d.__init__(self, fitpars, imaging_pars, fitparerr, sigma)
        (self.B, self.rxpx, self.rypx, self.theta) = fitpars[6:10]
        (self.Berr, self.rxpxerr, self.rypxerr) = fitparerr[6:]

    @property
    def N(self):
        return self.Nth + self.Nbec

    @property
    def Nth(self):
        "number of atoms in thermal cloud"
        print "thermal"  
        print self.imaging_pars.sigma0, self.A
        Nth = 1e-3 * 2*numpy.pi * \
              self.A/100. * self.sx*1e-6 * self.sx*1e-6 / self.imaging_pars.sigma0 
        return Nth

    @property
    def Nbec(self):
        "number of atoms in BEC"
        print "thermal"  
        print self.imaging_pars.sigma0, self.B,  self.rx,  self.ry
        Nbec = 1e-3*2*numpy.pi* \
               self.B/100. * self.rx*1e-6 * self.ry*1e-6 / self.imaging_pars.sigma0 
        return Nbec

    @property
    def OD(self):
        "optical density"
        print "koujiao"
        return (self.A + self.B)/100.0  # from the scaling factor in acquire

    def ODerr(self):
        "error optical density"
        return numpy.sqrt(self.Aerr**2 + self.Berr**2)/100.0
        
    @property
    def rx(self):
        print "pixel size"  
        print self.imaging_pars.pixelsize
        "Thomas-Fermi radius in �m"
        return abs(self.rxpx) * self.imaging_pars.pixelsize

    @property
    def ry(self):
        "Thomas-Fermi radius in �m"
        return abs(self.rypx) * self.imaging_pars.pixelsize

    @property
    def rxerr(self):
        "error Thomas-Fermi radius in �m"
        return abs(self.rxpxerr) * self.imaging_pars.pixelsize

    @property
    def ryerr(self):
        "error Thomas-Fermi radius in �m"
        return abs(self.rypxerr) * self.imaging_pars.pixelsize
        
    @property
    def T(self):
        "temperature of cloud in �K"
        if self.imaging_pars.expansion_time:
            return (self.sx*1e-6)**2 / \
                   (self.imaging_pars.expansion_time*1e-3)**2 * \
                   self.imaging_pars.mass / 1.38e-23 * 1e6
        else:
            return 0.0
        
    @property
    def Angle(self):
        return self.theta * 180./numpy.pi   

    def __str__(self):
        s = u"Dtb:%3.2f/%3.2f\n   �%3.2f/%3.2f\n"  \
            u"mxy:%3.0f/%3.0f px\n   �%3.1f/%3.1f\n" \
            u"sth:%3.0f �m\n   �%3.1f\n" \
            u"rxy:%3.0f/%3.0f �m\n   �%3.1f/%3.1f\n" \
            u"Tth:%5.3f �K\n   �%5.3f\n"\
            u"Nsb:%3.0f/%3.0f K \n" \
            u"Angle:%5.1f Deg" \
            %(self.A, self.B, self.Aerr, self.Berr,
              self.mx, self.my, self.mxerr, self.myerr,
              self.sx,  self.sxerr, 
              self.rx, self.ry, self.rxerr, self.ryerr,
              self.T, self.Terr,
              self.N,
              self.Nbec,
              self.Angle)
        return s


#class FitParsBoseBimodal2d(FitParsBimodal2d):
#    "Class for storing results of fit of 2d bimodal distribution to data"

#    description = "bose enhanced bimodal2d"

    #def __init__(self, fitpars, imaging_pars, fitparerr = numpy.zeros(9)):
    #    FitParsBimodal2d.__init__(self, fitpars, imaging_pars, fitparerr)

#    @property
#    def Nth(self):
#        "number of atoms in thermal cloud"
#        Nth = 1e-3 * 0.5*4.885*numpy.pi * \
#              self.A * self.sx*1e-6 * self.sx*1e-6 / self.imaging_pars.sigma0 
#        return Nth


class FitParsTF2d(FitPars):
    "Class for storing results of fit of 2d bimodal distribution to data"

    description = "Thomas-Fermi2d"

    fitparnames = ['N',  'Nerr',
                   'mx', 'mxerr',
                   'my', 'myerr',
                   'rx', 'rxerr',
                   'ry', 'ryerr',
                   'Nbec',
                   'OD', 'ODerr',
                   'sigma', 
                   'Angle']

    fitparunits = ['10^3','10^3',
                   'px', 'px', 'px', 'px',
                   '�m', '�m', '�m', '�m',
                   '10^3',
                   '', '',
                   '', 
                   'Deg']

    def __init__(self, fitpars, imaging_pars, fitparerr = numpy.zeros(7), sigma = 0.0):
        (self.mx, self.my, self.offset, self.B, self.rxpx, self.rypx, self.theta) = fitpars[0:7]
        (self.mxerr, self.myerr, self.offseterr,
         self.Berr, self.rxpxerr, self.rypxerr) = fitparerr[0:6]

        self.sigma = sigma
        self.valid=True
        self.imaging_pars=imaging_pars
    
    @property
    def N(self):
        return self.Nbec

    @property
    def Nerr(self):
        return 0.0 # TODO: not implemented!
    
    @property
    def OD(self):
        "optical density"
        return self.B/100.0   # scaling factor, the same as in gauss 2d fit 

    @property
    def ODerr(self):
        "error optical density"
        return self.Berr/100.0

    @property
    def Nbec(self):
        "number of atoms in BEC"
        Nbec = 1.25*1e-3* \
               self.B/100. * self.rx*1e-6 * self.ry*1e-6 / self.imaging_pars.sigma0 
        return Nbec
        
    @property
    def rx(self):
        "Thomas-Fermi radius in �m"
        return abs(self.rxpx) * self.imaging_pars.pixelsize

    @property
    def ry(self):
        "Thomas-Fermi radius in �m"
        return abs(self.rypx) * self.imaging_pars.pixelsize

    @property
    def rxerr(self):
        "error Thomas-Fermi radius in �m"
        return abs(self.rxpxerr) * self.imaging_pars.pixelsize

    @property
    def ryerr(self):
        "error Thomas-Fermi radius in �m"
        return abs(self.rypxerr) * self.imaging_pars.pixelsize
        
    @property
    def Angle(self):
        return self.theta * 180./numpy.pi   

    def __str__(self):
        s = u"OD:%3.2f �%3.2f\n"  \
            u"mx:%5.1f px �%3.2f\n" \
            u"my:%5.1f px �%3.2f\n" \
            u"rx:%5.1f �m �%3.2f\n" \
            u"ry:%5.1f �m �%3.2f\n" \
            u"Ntf:%3.0f K\n" \
            u"Angle:%5.1f Deg" \
            %(self.B, self.Berr,
              self.mx, self.mxerr,
              self.my, self.myerr,
              self.rx, self.rxerr,
              self.ry, self.ryerr,
              self.Nbec, self.theta*180./numpy.pi)
        return s


############################Test Fitting not sure if required.#################################

def test_fitting_bimodal():

    import roi
    import imagingpars

    ip = imagingpars.ImagingPars()

    fitg = Gauss2d(ip)
    fit2 = Bimodal2d(ip)
    fittf = ThomasFermi2d(ip)
    
    fit2.verbose = False #True

    fit2.cache.clear()
    
    x = numpy.linspace(-5,5,501)
    y = numpy.linspace(-3,3,301)

    x.shape = (1,-1)
    y.shape = (-1,1)

    pars = [0.1, 0, 0, 1, 1, 0, 1, 1, 1, 1]

    img = fit2.bimodal2d(pars, x, y, 0)
    #d   = fit2.Dbimodal2d(pars, x, y, 0)

    #img += numpy.random.standard_normal(img.shape)*0.9*0

    print img.max(), img.min()

    img = numpy.ma.masked_greater(img, 6.0)
    img.set_fill_value(6.0)
    print numpy.ma.count_masked(img), "pixel masked"

    imgfit, background, fitpars = fit2.do_fit(numpy.ma.array(img), roi.ROI( 100, 400, 10, 190))
    imgfitg, background, fitparsg = fitg.do_fit(numpy.ma.array(img), roi.ROI( 100, 400, 10, 190))
    imgfitth, background, fitparstf = fittf.do_fit(numpy.ma.array(img), roi.ROI( 100, 400, 10, 190))

    fac = 1e-3*1e-12*ip.pixelsize**2/ip.sigma0
    print "nsum", img.sum()*fac
    
    print fitpars.A, fitpars.B

    print (fitpars.__str__()).encode('ascii', 'ignore')

    print
    print (fitparsg.__str__()).encode('ascii', 'ignore')

    print
    print (fitparstf.__str__()).encode('ascii', 'ignore')


def test_fitting_bimodal_startpars():

    import roi
    import imagingpars

    import pylab as plt

    ip = imagingpars.ImagingPars()

    fit = Bimodal2d(ip)
    
    fit.verbose = False #True

    fit.cache.clear()
    
    x = numpy.linspace(-5,5,501)
    y = numpy.linspace(-3,3,301)

    x.shape = (1,-1)
    y.shape = (-1,1)

    A = 0.9
    B = 0.1
    s = 1.2
    r = 0.8

    pars = [A, 0, 0, s, s, 0, B, r, r, r]

    img = fit.bimodal2d(pars, x, y, 0)
    
    numpy.random.seed(0)
    img += numpy.random.standard_normal(img.shape)*0.2

    fit.verbose = True
    r = roi.ROI(0,500, 0, 300)
    imgfit, background, fitpars = fit.do_fit(numpy.ma.array(img), r)

    print fitpars.A, fitpars.B

    print (fitpars.__str__()).encode('ascii', 'ignore')

    #fitimg = fit2.bimodal2d(fitpar, x, y, 0)
    #plot(x.flat, sum(fitimg, 0))

    plt.figure(1)
    plt.clf()
    plt.subplot(211)
    plt.imshow(img)

    plt.subplot(212)
    print img.shape, img.sum(0).shape, x.shape
    plt.plot(x.flat, img.sum(0), 'b',
             x.flat[r.xrange_clipped(img)], imgfit[0].sum(0), 'r')
    plt.draw()    

def test_fitting_bosebimodal():

    import roi
    import imagingpars

    ip = imagingpars.ImagingPars()

    fit2 = BoseBimodal2d(ip)
    fit2.verbose = True
    fit2.cache.clear()
    
    x = numpy.linspace(-5,5,501)
    y = numpy.linspace(-3,3,301)

    x.shape = (1,-1)
    y.shape = (-1,1)

    #A, mx, my, sx, sy, offs, B, rx, ry = pars[0:9]
    pars = [1, 0.0456, 0.0456, 1, 1, 0, 1, 1, 1,1]

    img = fit2.bimodal2d(pars, x, y, 0)

    print img.max(), img.min()

    img = numpy.ma.masked_greater(img, 6.0)
    img.set_fill_value(6.0)
    print numpy.ma.count_masked(img), "pixel masked"

    imgfit, background, fitpars = fit2.do_fit(numpy.ma.array(img), roi.ROI( 100, 400, 10, 190))
    
    fac = 1e-3*1e-12*ip.pixelsize**2/ip.sigma0
    print "nsum", img.sum()*fac
    
    print fitpars.A, fitpars.B

    print (fitpars.__str__()).encode('ascii', 'ignore')


def test_fitting_gaussbose():

    import roi
    import imagingpars

    ip = imagingpars.ImagingPars()

    fit = GaussBose2d(ip)
    fit.verbose = True
    
    x = numpy.linspace(-5,5,501)
    y = numpy.linspace(-3,3,301)

    x.shape = (1,-1)
    y.shape = (-1,1)

    #A, mx, my, sx, sy, offs
    pars = [1, 0.0456, 0.0456, 1, 1, 0]

    img = fit.gaussbose2d(pars, x, y, 0)
    numpy.random.seed(0)
    img += numpy.random.standard_normal(img.shape)*0.2

    img = numpy.ma.masked_greater(img, 6.0)
    img.set_fill_value(6.0)
    print numpy.ma.count_masked(img), "pixel masked"

    imgfit, background, fitpars = fit.do_fit(numpy.ma.array(img), roi.ROI( 100, 400, 10, 190))
    
    fac = 1e-3*1e-12*ip.pixelsize**2/ip.sigma0
    print "nsum", img.sum()*fac
    print (fitpars.__str__()).encode('ascii', 'ignore')


def test_fitting_gauss():

    import roi
    import imagingpars

    ip = imagingpars.ImagingPars()

    fit = Gauss2d(ip)
    fit.verbose = True
    
    x = numpy.linspace(-5,5,501)
    y = numpy.linspace(-3,3,301)

    x.shape = (1,-1)
    y.shape = (-1,1)

    #A, mx, my, sx, sy, offs
    pars = [1, 0.0456, 0.0456, 1, 1, 0]

    img = fit.gauss2d(pars, x, y, 0)
    numpy.random.seed(0)
    img += numpy.random.standard_normal(img.shape)*0.2

    img = numpy.ma.masked_greater(img, 6.0)
    img.set_fill_value(6.0)
    print numpy.ma.count_masked(img), "pixel masked"

    imgfit, background, fitpars = fit.do_fit(numpy.ma.array(img), roi.ROI( 100, 400, 10, 190))
    
    fac = 1e-3*1e-12*ip.pixelsize**2/ip.sigma0
    print "nsum", img.sum()*fac
    print (fitpars.__str__()).encode('ascii', 'ignore')



if __name__ == '__main__':
    import profile
    #profile.run('test_fitting_bimodal()')
    #test_fitting_bimodal()
    #test_fitting_bimodal_startpars()
    #test_fitting_bosebimodal()
    test_fitting_gauss()
    test_fitting_gaussbose()
 ##############################################End of Test Fitting#####################################
