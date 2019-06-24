"""bluesky.extrafilewriters.SMOKEready

Writes smokeready files in the form:

    ¯\\_(ツ)_//¯

"""
import pdb
import os
import logging
from datetime import timedelta, datetime

import numpy as np
from bluesky.config import Config
from bluesky import locationutils

class ColumnSpecificRecord(object):
    columndefs = []
    has_newline = True
    
    def __init__(self):
        object.__setattr__(self, "data", dict())

    def __setattr__(self, key, value):
        object.__getattribute__(self, "data")[key] = value

    def __getattr__(self, key):
        if key.startswith('_'):
            raise AttributeError(key)
        return object.__getattribute__(self, "data")[key]

    def __str__(self):
        outstr = ""
        for (fieldlen, name, datatype) in self.columndefs:
            try:
                data = self.data[name]
            except KeyError:
                data = None
            if data is None:
                data = ""
            elif datatype is float:
                if np.isNaN(data):
                    data = ""
                elif fieldlen < 5:
                    data = str(int(data))
                elif fieldlen < 8:
                    data = "%5.4f" % data
                else:
                    data = "%8.6f" % data
            else:
                data = str(datatype(data))
            if len(data) > fieldlen:
                data = data[:fieldlen]
            if datatype is str:
                data = data.ljust(fieldlen, ' ')
            else:
                data = data.rjust(fieldlen, ' ')
            outstr += data
        return outstr + (self.has_newline and '\n' or '')

class PTINVRecord(ColumnSpecificRecord):
    has_newline = False
    columndefs = [ (  2, "STID",     int),
                   (  3, "CYID",     int),
                   ( 15, "PLANTID",  str),
                   ( 15, "POINTID",  str),
                   ( 12, "STACKID",  str),
                   (  6, "ORISID",   str),
                   (  6, "BLRID",    str),
                   (  2, "SEGMENT",  str),
                   ( 40, "PLANT",    str),
                   ( 10, "SCC",      str),
                   (  4, "BEGYR",    int),
                   (  4, "ENDYR",    int),
                   (  4, "STKHGT",   float),
                   (  6, "STKDIAM",  float),
                   (  4, "STKTEMP",  float),
                   ( 10, "STKFLOW",  float),
                   (  9, "STKVEL",   float),
                   (  8, "BOILCAP",  float),
                   (  1, "CAPUNITS", str),
                   (  2, "WINTHRU",  float),
                   (  2, "SPRTHRU",  float),
                   (  2, "SUMTHRU",  float),
                   (  2, "FALTHRU",  float),
                   (  2, "HOURS",    int),
                   (  2, "START",    int),
                   (  1, "DAYS",     int),
                   (  2, "WEEKS",    int),
                   ( 11, "THRUPUT",  float),
                   ( 12, "MAXRATE",  float),
                   (  8, "HEATCON",  float),
                   (  5, "SULFCON",  float),
                   (  5, "ASHCON",   float),
                   (  9, "NETDC",    float),
                   (  4, "SIC",      int),
                   (  9, "LATC",     float),
                   (  9, "LONC",     float),
                   (  1, "OFFSHORE", str) ]

class PTINVPollutantRecord(ColumnSpecificRecord):
    has_newline = False
    columndefs = [ ( 13, "ANN",  float),
                   ( 13, "AVD",  float),
                   (  7, "CE",   float),
                   (  3, "RE",   float),
                   ( 10, "EMF",  float),
                   (  3, "CPRI", int),
                   (  3, "CSEC", int) ]

class PTDAYRecord(ColumnSpecificRecord):
    columndefs = [ (  2, "STID",    int),
                   (  3, "CYID",    int),
                   ( 15, "FCID",    str),
                   ( 12, "SKID",    str),
                   ( 12, "DVID",    str),
                   ( 12, "PRID",    str),
                   (  5, "POLID",   str),
                   (  8, "DATE",    str),
                   (  3, "TZONNAM", str),
                   ( 18, "DAYTOT",  float),
                   (  1, "-dummy-", str),
                   ( 10, "SCC",     str) ]

class PTHOURRecord(ColumnSpecificRecord):
    columndefs = [ (  2, "STID",    int),
                   (  3, "CYID",    int),
                   ( 15, "FCID",    str),
                   ( 12, "SKID",    str),
                   ( 12, "DVID",    str),
                   ( 12, "PRID",    str),
                   (  5, "POLID",   str),
                   (  8, "DATE",    str),
                   (  3, "TZONNAM", str),
                   (  7, "HRVAL1",  float),
                   (  7, "HRVAL2",  float),
                   (  7, "HRVAL3",  float),
                   (  7, "HRVAL4",  float),
                   (  7, "HRVAL5",  float),
                   (  7, "HRVAL6",  float),
                   (  7, "HRVAL7",  float),
                   (  7, "HRVAL8",  float),
                   (  7, "HRVAL9",  float),
                   (  7, "HRVAL10", float),
                   (  7, "HRVAL11", float),
                   (  7, "HRVAL12", float),
                   (  7, "HRVAL13", float),
                   (  7, "HRVAL14", float),
                   (  7, "HRVAL15", float),
                   (  7, "HRVAL16", float),
                   (  7, "HRVAL17", float),
                   (  7, "HRVAL18", float),
                   (  7, "HRVAL19", float),
                   (  7, "HRVAL20", float),
                   (  7, "HRVAL21", float),
                   (  7, "HRVAL22", float),
                   (  7, "HRVAL23", float),
                   (  7, "HRVAL24", float),
                   (  8, "DAYTOT",  float),
                   (  1, "-dummy-", str),
                   ( 10, "SCC",     str) ]


class SmokeReadyWriter(object):

  def __init__(self, dest_dir, **kwargs):
    # make dynamic to accept args
    self.filedt = datetime.now()

    ptinv = (kwargs.get('ptinv_filename') or
      Config.get('extrafiles', 'smokeready', 'ptinv_filename'))
    ptinv = self.filedt.strftime(ptinv)
    self._ptinv_pathname = os.path.join(dest_dir, ptinv)

    ptday = (kwargs.get('ptday_filename') or
      Config.get('extrafiles', 'smokeready', 'ptday_filename'))
    ptday = self.filedt.strftime(ptday)
    self._ptday_pathname = os.path.join(dest_dir, ptday)

    pthour = (kwargs.get('pthour_filename') or
      Config.get('extrafiles', 'smokeready', 'pthour_filename'))
    pthour = self.filedt.strftime(pthour)
    self._pthour_pathname = os.path.join(dest_dir, pthour)
   

  def write(self, fires_manager):
    fires_info = fires_manager.fires
    country_process_list = ['US', 'USA', 'United States']

    ptinv = open(self._ptinv_pathname, 'w')
    ptday = open(self._ptday_pathname, 'w')
    pthour = open(self._pthour_pathname, 'w')

    ptinv.write("#IDA\n#PTINV\n#COUNTRY %s\n" % country_process_list[0])
    ptinv.write("#YEAR %d\n" % self.filedt.year)
    ptinv.write("#DESC POINT SOURCE BlueSky Framework Fire Emissions\n")
    ptinv.write("#DATA PM2_5 PM10 CO NH3 NOX SO2 VOC\n")

    ptday.write("#EMS-95\n#PTDAY\n#COUNTRY %s\n" % country_process_list[0])
    ptday.write("#YEAR %d\n" % self.filedt.year)
    ptday.write("#DESC POINT SOURCE BlueSky Framework Fire Emissions\n")

    pthour.write("#EMS-95\n#PTHOUR\n#COUNTRY %s\n" % country_process_list[0])
    pthour.write("#YEAR %d\n" % self.filedt.year)
    pthour.write("#DESC POINT SOURCE BlueSky Framework Fire Emissions\n")

    num_of_fires = 0
    skip_no_emiss = 0
    skip_no_plume = 0
    skip_no_fips = 0
    skip_no_country = 0
    total_skipped = 0

    for fire_info in fires_info:
      for fire_loc in fire_info.locations:
        pdb.set_trace()
        if fire_loc["emissions"] is None:
          skipNoEmis += 1
          totalSkip += 1
          continue

        if fire_loc["plumerise"] is None:
          skipNoPlume += 1
          totalSkip += 1
          continue

        if fire_loc['fips'] is None or fireLoc['fips'] == "-9999":
          skipNoFips += 1
          totalSkip += 1
          continue

        if fire_loc['country'] not in countryProcessList:
          skipNoCountry += 1
          totalSkip += 1
          continue
    pdb.set_trace()


  def _write_ptinv_file(self):
    ptinv = open(self._ptinv_pathname, 'w')
    ptinv.write("#IDA\n#PTINV\n#COUNTRY %s\n" % country_process_list[0])
    ptinv.write("#YEAR %d\n" % self.filedt.year)
    ptinv.write("#DESC POINT SOURCE BlueSky Framework Fire Emissions\n")
    ptinv.write("#DATA PM2_5 PM10 CO NH3 NOX SO2 VOC\n")

  def _write_ptday_file(self):
    ptday = open(self._ptday_pathname, 'w')
    ptday.write("#EMS-95\n#PTDAY\n#COUNTRY %s\n" % country_process_list[0])
    ptday.write("#YEAR %d\n" % self.filedt.year)
    ptday.write("#DESC POINT SOURCE BlueSky Framework Fire Emissions\n")

  def _write_pthour_file(self):
    pthour = open(self._pthour_pathname, 'w')
    pthour.write("#EMS-95\n#PTHOUR\n#COUNTRY %s\n" % country_process_list[0])
    pthour.write("#YEAR %d\n" % self.filedt.year)
    pthour.write("#DESC POINT SOURCE BlueSky Framework Fire Emissions\n")