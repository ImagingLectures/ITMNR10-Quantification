import numpy as np
import matplotlib.pyplot as plt
import skimage.filters as flt
import skimage.morphology as morph
from skimage.measure import label, regionprops_table
from skimage.segmentation import watershed
from scipy.ndimage import distance_transform_edt as edt
from sklearn.metrics import confusion_matrix
import pandas as pd
from tqdm.notebook import tqdm

import scipy.ndimage as nd

import sys
sys.path.append('/Users/kaestner/git/scripts/python')
# import amglib.plotsupport as ps
import amglib.readers as rd


def make_random_data(N, sigma=3,seed = 12345) :
    np.random.seed(seed)
    f  = np.random.normal(size=[N,N,N])
    ff = flt.gaussian(f,sigma=sigma)
    s = ff.std()
    
    return (0.5*s<ff).astype(float)

def make_balls(N,radius,space=0) :
    b0 = morph.ball(radius=radius)
    b  = np.zeros([b0.shape[0]+space,b0.shape[1]+space,b0.shape[2]+space])
    s2 = space//2
    b[s2:b0.shape[0]+s2,s2:b0.shape[1]+s2,s2:b0.shape[2]+s2]=b0
    B = np.tile(b,[N,N,N])
    
    
    return B.astype(float)

def ruin_data(img,snr,blurr) :
    bimg = img
    if 0<blurr :
        bimg = flt.gaussian(img,sigma=blurr)

    nimg = bimg + np.random.normal(size=bimg.shape, scale=1.0/snr)
    
    return nimg

def label_img(x,marker=None,radius=4) :
    if marker is None :
        marker = morph.erosion(x,footprint=morph.ball(radius=radius))
    lmarker = label(marker)
    d = edt(x)
    
    labels = watershed(-d, lmarker,mask=x)
    
    return labels

def surface_area(x) :
    s = x-morph.erosion(x,footprint=morph.ball(1))
    
    return s


def processing_workflow_00(x,radius, sigma) : # threshold raw image
    th = flt.threshold_otsu(x)
    thx = th<x
    
    return thx

def processing_workflow_01(x,radius, sigma) : # threshold raw image
    th = flt.threshold_otsu(x)
    thx = th<x
    
    if 0<radius :
        o = morph.binary_opening(thx,footprint = morph.ball(radius=radius))
        c = morph.binary_closing(o,footprint = morph.ball(radius=radius))
    
    return c

def processing_workflow_02(x,radius, sigma) : # threshold raw image
    if 0 < sigma :
        x  = flt.gaussian(x,sigma=sigma) 

    th = flt.threshold_otsu(x)
    thx = th<x
    
    if 0 < radius :
        o = morph.binary_opening(thx,footprint = morph.ball(radius=radius))
        c = morph.binary_closing(o,footprint = morph.ball(radius=radius))
    else :
        c = thx
    
    return c

def analyze_spheres(radius) :
    res = []
    for r in tqdm(radius) :
        r2 = r+1
        l  = np.linspace(-r2,r2,2*r2+1)
        x,y,z = np.meshgrid(l,l,l)
        
        R = np.sqrt(x**2+y**2+z**2)
        sphere = (R<=r).astype(float)
        v = sphere.sum()
        s = surface_area(sphere).sum()
        
        gv = 4/3 * np.pi * r**3
        gs = 4 * np.pi * r**2
        res.append({'radius' : r, 'vol_voxel' : v, 'surf_voxel' : s, 'vol_geo' : gv, 'surf_geo' : gs, 'vol_ratio' : v/gv, 'surf_ratio' : s/gs, 'vol_error' : np.abs(v-gv)/gv, 'surf_error' : np.abs(s-gs)/gs})
        
    df = pd.DataFrame(res)
    
    return df
        

def analysis_workflow_01(img,marker) :
    lbl   = label_img(img, marker = marker); 
    ss    = surface_area(lbl)
    surf_cnt = nd.histogram(ss[0<ss].ravel(),1,ss.max(),ss.max())
    vol_cnt  = nd.histogram(lbl[0<lbl].ravel(),1,lbl.max(),lbl.max())

    res = {'vol' : vol_cnt,'vol_avg': vol_cnt.mean(), 'vol_std': vol_cnt.std(), 'surf' : surf_cnt ,'surf_avg': surf_cnt.mean(), 'surf_std': surf_cnt.std()}

    return res

def evaluation(img, snr, blurr, radius, sigma) :

    lbl_orig    = label_img(img)
    marker_orig = morph.erosion(lbl_orig)

    results = []
    for s in tqdm(snr) :
        for b in blurr :
            raw_img = ruin_data(img,snr=s,blurr=b)

            for r in radius :
                for si in sigma :

                    seg_img = processing_workflow_02(raw_img,radius=r,sigma=si)
                    res = analysis_workflow_01(seg_img,marker=marker_orig)
                    res.update({'snr' : s, 'blurr' : b, 'radius' : r, 'sigma' : si})

                    results.append(res)

    df = pd.DataFrame(results)
    return df
                    