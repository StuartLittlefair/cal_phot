import json
import requests
from pprint import pprint
import os
import hipercam as hcam
import numpy as np

from astropy import time, coordinates as coord, units as u
from astropy.coordinates import AltAz

from logger import printer

'''

This script is going to take a list of co-ordinates, and use that to query SDSS for the magnitudes 
of those stars.

SDSS REST format:
    GET or POST /radialSearch
    Prameters      - Expected Values
    Ra             - Right Ascention in degrees
    Dec            - Declination in degrees
    radius         - Radius in arcminutes
    format         - output file format. E.g. csv,html,xml
    whichway       - Specify Equitorial or Galactic
    uband          - Specify comma seperated range e.g 0,20. This is an optional parameter for SDSS U band.
    gband          - Specify comma seperated range e.g 0,20. This is an optional parameter for SDSS G band.
    rband          - Specify comma seperated range e.g 0,20. This is an optional parameter for SDSS R band.
    iband          - Specify comma seperated range e.g 0,20. This is an optional parameter for SDSS I band.
    zband          - Specify comma seperated range e.g 0,20. This is an optional parameter for SDSS Z band.
    whichquery     - imaging or spectra

    Example:
    http://skyserver.sdss.org/dr12/SkyserverWS/SearchTools/
    RadialSearch?ra=258.2&dec=64&radius=4.1&whichway=equitorial&
    limit=10&format=json&fp=none&uband=0,17&gband=0,15&whichquery=imaging

It will construct a dict of the magnitudes from the result and return it.

'''

def deg2arcsec(inp, ra):
    sign = '+'
    if inp < 0:
        inp = -inp
        sign = '-'
    
    if ra:
        hh = (24./360.) * inp
    else:
        hh = inp
    mm = (hh - int(hh)) * 60
    ss = (mm - int(mm)) * 60
    
    hh = int(hh)
    mm = int(mm)
    
    output = '{}{:d}:{:d}:{:.2f}'.format(sign, hh, mm, ss)

    return output


def construct_reference(fetchFname):
    '''
    Queries the SDSS database for the magnitudes of the stars contained in <fetchFname>, returns them as a dict of lists.

    mags = {
        '1': [ap1, ap2, ap3],      # r' band
        '2': [ap1, ap2],           # g' band
        '3': [ap1, ap2, ap3, ap4]  # u' band
    }

    <fetchFname> is formatted as follows:
        "CCD 1 reference 1 RA" "CCD 1 reference 1 Dec"
        "CCD 1 reference 2 RA" "CCD 1 reference 2 Dec"

        "CCD 2 reference 1 RA" "CCD 2 reference 1 Dec"
        "CCD 2 reference 2 RA" "CCD 2 reference 2 Dec"
        "CCD 2 reference 3 RA" "CCD 2 reference 3 Dec"

        "CCD 3 reference 1 RA" "CCD 3 reference 1 Dec"
        "CCD 3 reference 2 RA" "CCD 3 reference 2 Dec"


    Arguments:
    ----------
    fetchFname: string
        File containing the RA and Dec of the stars, in the format above
    

    Returns:
    --------
    mags: dict
        Dictionary containing the magnitudes of the stars in the relevant band.
    '''

    printer("\n\n--- Getting reference SDSS magnitudes from '{:s}' ---".format(fetchFname.split('/')[-1]))

    CCDs = ['1', '2', '3']
    radius = '0.1' # search radius, arcseconds

    fetchme = {
        "1": [],
        "2": [],
        "3": []
    }
    
    if not os.path.isfile(fetchFname):
        printer("The file I was passed, {}, does not exist!".format(fetchFname))
        # Check that we;ve not been given a directory with a 'coord_list' file in it:
        test = fetchFname.split('/')
        test.append('coord_list.coords')
        test = '/'.join(test)
        if os.path.isfile(test):
            fetchFname = test
            printer("I did, however, find a file called {}. Using that instead...".format(fetchFname))
        # If not, then we have no file. Create a template.
        else:
            with open(fetchFname, 'w') as f:
                f.write('<CCD 1 reference 1 RA> <CCD 1 reference 1 Dec>\n')
                f.write("<CCD 1 reference 2 RA> <CCD 1 reference 2 Dec>\n")
                f.write("\n")
                f.write("<CCD 2 reference 1 RA> <CCD 2 reference 1 Dec>\n")
                f.write("<CCD 2 reference 2 RA> <CCD 2 reference 2 Dec>\n")
                f.write("<CCD 2 reference 3 RA> <CCD 2 reference 3 Dec>\n")
                f.write("\n")
                f.write("<CCD 3 reference 1 RA> <CCD 3 reference 1 Dec>\n")
                f.write("<CCD 3 reference 2 RA> <CCD 3 reference 2 Dec>\n")
            printer("Couldn't find that co-ordinate list! I created a template for you at the location you gave me, {}".format(fetchFname))
            raise FileNotFoundError

    printer("Getting SDSS magnitudes for the coordinates found in {}".format(fetchFname))

    with open(fetchFname) as f:
        x = 1
        for line in f:
            if line[0] == '#':
                # print(line.strip())
                pass
            elif len(line.split()) != 2:
                x += 1
            else:
                fetchme[str(x)].append(line.split())

    toWrite = {
        '1':[],
        '2':[],
        '3':[]
    }

    bands = ['', 'r', 'g', 'u']

    for CCD in CCDs:
        printer('-> CCD {}'.format(CCD))
        # Grab the list of coordinates we want to query
        coords = fetchme[CCD]

        for i, coord in enumerate(coords):
            ra, dec = coord

            printer('    Searching -> RA, Dec: {}, {}'.format(ra, dec))

            # Construct the URL we're gonna post. First define what DB we want to search
            url  = 'http://skyserver.sdss.org/dr14/SkyserverWS/SearchTools/RadialSearch?'
            url += 'ra={}&dec={}&'.format(ra, dec)
            # I'm using a radial search, this is the readius of that search
            url += 'radius={}&'.format(radius)
            # Which coord system are we using. Can't imagine I'll want galactic...
            url += 'whichway=equitorial&'
            # If I'm getting more than 5 results, I've probably picked a crappy reference anyway...
            url += 'limit=5&'
            url += 'format=json&'
            url += 'whichquery=imaging'

            resp = requests.post(url)

            # pprint(resp.json())

            results = resp.json()[0]['Rows']
            if len(results) >= 5:
                printer('You got a lot of results from the SDSS query! Choose from the following VERY carefully.')
            if len(results) > 1:
                printer("--------------------------------------------\nMore than one object found at that location!")
                # Get the user to pick one:
                for m, line in enumerate(results):
                    printer("{}\n  RA: {}, Dec: {}\n  u: {}\n  g: {}\n  r: {}".format(
                        m, line['ra'], line['dec'], 
                        line['u'], line['g'], line['r']
                        )
                    )
                n = input("Which object to use?: ")
                printer("Chose object {}".format(n), terminal=False)
                target = results[int(n)]
                printer('--------------------------------------------')
            elif len(results) == 1:
                target = results[0]
                ra = deg2arcsec(target['ra'], ra=True)
                dec = deg2arcsec(target['dec'], ra=False)
                printer("    Found one result:\n      ra: {}, dec: {}\n        u: {}\n        g: {}\n        r: {}".format(
                        ra, dec, 
                        target['u'], target['g'], target['r']
                        )
                    )
            else:
                printer('ERROR! Found no targets at the location: RA: {}, Dec: {}'.format(target['ra'], target['dec']))
                printer('Try broadening the search radius in this script (was {}),'.format(radius))
                printer('and make sure that your targets are definitely in the SDSS field!')
                raise LookupError

            # pprint(target)
            toWrite[CCD].append(
                target[ bands[int(CCD)] ]
            )
    
        toWrite[CCD] = np.array(toWrite[CCD])

    printer("Done!\n")
    return toWrite

def get_instrumental_mags(data, coords=None, obsname=None, ext=None):
    '''
    Takes a hipercam data object, and exctracts the instrumental magnitude of each aperture in each CCD

    If Coords and an observatory are supplied, also correct for airmass, using supplied extinction coeffiecients

    
    Arguments:
    ----------
    data: hipercam.Tseries
        The data to analyse
    
    coords: str
        Optional. Ra, Dec of the data. Must be readable by Astropy.
    
    obsname: str
        Optional. Observing location name of the data. 


    Returns:
    --------
    all_mags: dict
        Dict, with the keys corresponding to the CCD numbers. Each entry is a numpy array of the 
        instrumental magnitudes, in the order they're found in the aperture list.
    '''
    printer("------- Getting instrumental magnitude -------")
    #TODO: I need to make the extinction coefficient different in each band.

    if coords != None and obsname != None:
        printer("-> I'm correcting for airmass, using the following:")
        printer("     Extinction: {} mags/airmass".format(ext))
        printer("        Ra, Dec: {}".format(coords))
        printer("    Observatory: {}".format(obsname))
        
        # Where are we?
        observatory = coord.EarthLocation.of_site(obsname)
        star_loc = coord.SkyCoord(
            coords,
            unit=(u.hourangle, u.deg), frame='icrs')

        # I want altitude converted to zenith angle. Airmass is roughly constant over 
        # a single eclipse so only do it once to save time.
        obs_T = float(data['1'][0][1])
        obs_T = time.Time(obs_T, format='mjd')
        star_loc_AltAz = star_loc.transform_to(AltAz(obstime=obs_T, location=observatory))
        zenith_angle = 90. - star_loc_AltAz.alt.value
        airmass = 1. / np.cos(np.radians(zenith_angle))
        printer("  For the observations at {}, calculated altitude of {:.3f}, and airmass of {:.3f}\n".format(
            obs_T.iso, star_loc_AltAz.alt.value, airmass))
    else:
        airmass = 0.0


    all_mags = {}
    aps = data.apnames


    for CCD in aps:
        # Get this frame's apertures
        ap = sorted(aps[CCD])

        ex = ext[int(CCD)-1]

        star = data.tseries(CCD, '1')

        # mean star counts/s, converted to magnitudes
        fl = np.zeros(len(star.y))

        # I have to loop through the exposure times manually, as I can't figure out how to extract them with a built-in
        # and they're stored as a weird object that doesn't have a slice option...
        for i, count in enumerate(star.y):
            # the third column, data[CCD][i][3], contains the exposure time for that frame
            fl[i] = count / data[CCD][i][3]

        # Calculate the mean apparent magnitude of the star above the atmosphere
        mag = -2.5*np.log10(np.mean(fl))
        # star magnitudes
        mags = [mag]
        
        # If we have more than one star, handle that
        if len(ap) > 1:
            for comp in ap[2:]:
                # Store the star in a temp variable
                s = data.tseries(CCD, comp)
                star = star + s

                # Get the count flux of the star
                fl = np.zeros(len(s.y))
                for i, count in enumerate(s.y):
                    #               \/ This is the exposure time for that frame
                    fl[i] = count / float(data[CCD][i][3])

                # Instrumental magnitude
                mag = -2.5*np.log10(np.mean(fl))
                mags.append(mag)
        
        printer("  CCD {} extinction: {:.3f} mags".format(CCD, ex*airmass))
        
        mags = np.array(mags)
        
        printer("    Before applying extinction correction:")
        printer(mags)

        # Add the light lost to atmosphere back in
        mags = mags - (ex*airmass)

        printer("    After extinction correction:")
        printer(mags)

        all_mags[CCD] = mags
    return all_mags

def get_comparison_magnitudes(std_fname, comp_fname, std_coords, comp_coords,
                                std_mags, obsname, ext):
    '''
    Takes two .log files, one containing the reduction of a standard star and the other the reduction of
    the target frame, using the same settings (aperture size, extraction method, etc.). Uses this to 
    compute the apparent magnitudes of comparison stars in comp_fname

    Requires the RA and Dec to correct for airmass.

    Arguments:
    ----------
    std_fname: str
        file containing the standard observations
    comp_fname: str
        file containing the target frame, reduced with identical parameters as the standard
    std_coords: str
        String containing the RA and Dec of the standard, in a style astropy can take.
    comp_coords: str
        String containing the RA and Dec of the target frame, in a style astropy can take.
    std_mags: list
        list containing the SDSS magnitude of the standard in each CCD, inorder
    obsname: str
        Observatory name
    ext: list
        Extinction coefficients, in order of CCD

    Returns:
    --------
    '''
    printer("\n\n--- Extracting comparison star SDSS magnitudes from the file '{}'---".format(comp_fname))
    printer("     using the standard star found in {}\n".format(std_fname))

    std_mags = np.array(std_mags)

    standard_data = hcam.hlog.Hlog.from_ascii(std_fname)
    comp_data     = hcam.hlog.Hlog.from_ascii(comp_fname)

    printer("-----------------  STANDARD  -----------------")
    # Extract the instrumental magnitudes of the standard
    instrumental_std_mags = get_instrumental_mags(standard_data, std_coords, obsname, ext)
    # Convert the dict recieved into a list
    instrumental_std_mags = [instrumental_std_mags[str(i+1)][0] for i in range(len(instrumental_std_mags))]
    instrumental_std_mags = np.array(instrumental_std_mags)
    # The zero points are the difference between observed and expected.
    zero_points = instrumental_std_mags - std_mags
    
    printer("\n  Standard star instrumental magnitudes: ")
    for i, m in enumerate(instrumental_std_mags):
        printer("    CCD {}: {:3.3f}".format(i, m))
    
    printer("\n  Standard Star SDSS magnitudes:")
    for i, m in enumerate(std_mags):
        printer("    CCD {}: {:3.3f}".format(i, m))
    
    printer("\n  Zero points in each band (in order of CCD, will be subtracted from the inst. mags):")
    for i, m in enumerate(zero_points):
        printer("    CCD {}: {:3.3f}".format(i, m))

    printer("\n----------------- COMPARISON -----------------")
    instrumental_comp_mags = get_instrumental_mags(comp_data, comp_coords, obsname, ext)


    printer("\n  Comparison star instrumental magnitudes:")
    for CCD in instrumental_comp_mags:
        printer("    CCD {}: {}".format(CCD, 
            np.array2string(instrumental_comp_mags[CCD], precision=3) ))

    printer("\n  Comparison star apparent magnitudes:")
    apparent_comp_mags = instrumental_comp_mags.copy()
    for i, CCD in enumerate(apparent_comp_mags):
        apparent_comp_mags[CCD] -= zero_points[i]
    for CCD in apparent_comp_mags:
        printer("    CCD {}: {}".format(CCD, 
            np.array2string(apparent_comp_mags[CCD], precision=3) ))

    printer('\n  --- Done getting magnitudes ---\n\n')
    return apparent_comp_mags