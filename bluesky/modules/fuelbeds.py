"""bluesky.modules.fuelbeds"""

__author__ = "Joel Dubowy"

import logging
import random
from collections import defaultdict

import fccsmap
from fccsmap.lookup import FccsLookUp
from functools import reduce

from bluesky.config import Config

__all__ = [
    'run'
]

__version__ = "0.1.0"

def run(fires_manager):
    """Runs emissions module

    Args:
     - fires_manager -- bluesky.models.fires.FiresManager object
    """
    logging.info("Running fuelbeds module")
    fires_manager.processed(__name__, __version__,
        fccsmap_version=fccsmap.__version__)

    fuelbeds_config = Config.get('fuelbeds')
    logging.debug('Using FCCS version %s', fuelbeds_config['fccs_version'])

    for fire in fires_manager.fires:
        with fires_manager.fire_failure_handler(fire):
            if not fire.get('growth'):
                raise ValueError(
                    "Growth information required to look up fuelbeds")

            for g in fire['growth']:
                if not g.get('location'):
                    raise ValueError(
                        "growth location information required to look up fuelbeds")
                # TODO: instead of instantiating a new FccsLookUp and Estimator
                #   for each growth object, create AK and non-AK lookup and
                #   estimator objects that are reused, and set reference to
                #   correct one here
                lookup = FccsLookUp(is_alaska=g['location'].get('state')=='AK',
                    **fuelbeds_config)
                Estimator(lookup, **fuelbeds_config).estimate(g)

    # TODO: Add fuel loadings data to each fuelbed object (????)
    #  If we do so here, use bluesky.modules.consumption.FuelLoadingsManager
    #  (which should maybe be moved to a common module if to be used here)
    #     fm = FuelLoadingsManager()
    #     for fire in fires_manager.fires:
    #       for fb in get_fuel_loadings():
    #         fb['fuel_loadings'] = fm.get_fuel_loadings(fb['fccs_id'])
    #  Note: probably no need to do this here since we do it in the
    #  consumption module

    fires_manager.summarize(fuelbeds=summarize(fires_manager.fires))

def summarize(fires):
    if not fires:
        return []

    area_by_fccs_id = defaultdict(lambda: 0)
    total_area = 0
    for fire in fires:
        for g in fire['growth']:
            total_area += g['location']['area']
            for fb in g['fuelbeds']:
                area_by_fccs_id[fb['fccs_id']] += (fb['pct'] / 100.0) * g['location']['area']
    summary = [{"fccs_id": fccs_id, "pct": (area / total_area) * 100.0}
        for fccs_id, area in area_by_fccs_id.items()]
    return sorted(summary, key=lambda a: a["fccs_id"])

# TODO: change 'get_*' functions to 'set_*' and chnge fire in place
# rather than return values ???

# According to https://en.wikipedia.org/wiki/Acre, an acre is 4046.8564224 m^2
ACRES_PER_SQUARE_METER = 1 / 4046.8564224  # == 0.0002471053814671653
# Allow summed fuel percentages to be between 99.5% and 100.5%
# TODO: Move to common constants module? (timeprofiling defines similar
# constant for total growth percentage)
TOTAL_PCT_THRESHOLD = 0.5

class Estimator(object):

    def __init__(self, lookup, **options):
        self.lookup = lookup

        for attr, default in options.items():
            if attr.startswith('truncation_'):
                # if user override defaults by setting to None or 0, we
                # won't truncate by that criterion
                setattr(self, attr, options[k])

    def estimate(self, growth_obj):
        """Estimates fuelbed composition based on lat/lng or GeoJSON data.

        If growth_obj['location']['geojson'] is defined, it will look something like
        the following:

            {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [-84.8194, 30.5222],
                            [-84.8197, 30.5209],
                            ...
                            [-84.8193, 30.5235],
                            [-84.8194, 30.5222]
                        ]
                    ]
                ]
            }
        """
        if not growth_obj.get('location'):
            raise ValueError("Insufficient data for looking up fuelbed information")

        fuelbed_info = {}
        if growth_obj['location'].get('shape_file'):
            raise NotImplementedError("Importing of shape data from file not implemented")

        elif growth_obj['location'].get('geojson'):
            fuelbed_info = self.lookup.look_up(growth_obj['location']['geojson'])
            # fuelbed_info['area'] is in m^2
            # TDOO: only use fuelbed_info['area'] if growth_obj['location']['area']
            # isn't already defined?
            if fuelbed_info and fuelbed_info.get('area'):
                growth_obj['location']['area'] = fuelbed_info['area'] * ACRES_PER_SQUARE_METER

        elif growth_obj['location'].get('latitude') and growth_obj['location'].get('longitude'):
            geo_data = {
                "type": "Point",
                "coordinates": [
                    growth_obj['location']['longitude'],
                    growth_obj['location']['latitude']
                ]
            }
            logging.debug("Converted lat,lng to geojson: %s", geo_data)
            fuelbed_info = self.lookup.look_up(geo_data)

        else:
            raise ValueError("Insufficient data for looking up fuelbed information")

        if not fuelbed_info or not fuelbed_info.get('fuelbeds'):
            # TODO: option to ignore failures ?
            raise RuntimeError("Failed to lookup fuelbed information")
        elif TOTAL_PCT_THRESHOLD < abs(100.0 - sum(
                [d['percent'] for d in fuelbed_info['fuelbeds'].values()])):
            raise RuntimeError("Fuelbed percentages don't add up to 100% - {fuelbeds}".format(
                fuelbeds=fuelbed_info['fuelbeds']))

        fuelbeds = [{'fccs_id':f, 'pct':d['percent']}
            for f,d in fuelbed_info['fuelbeds'].items()]

        growth_obj.update(**self._truncate(fuelbeds))

    def _truncate(self, fuelbeds):
        """Sorts fuelbeds by decreasing percentage, and

        Sort fuelbeds by decreasing percentage, use first N fuelbeds that
        reach 90% coverage or 5 count (defaults, both configurable), and
        then adjust percentages of included growth_objs so that total is 100%.
        e.g. if 3 fuelbeds, 85%, 8%, and 7%, use only the first and second,
        and then adjust percentages as follows:
          85% -> 85% * 100 / (100 - 7) = 91.4%
          8% -> 7% * 100 / (100 - 7) = 8.6%
        """
        truncated_fuelbeds = []
        total_pct = 0.0
        # iterate through fuelbeds sorted by pct (decreasing) and then by
        # fccs_id (for deterministic results in the case of equal percentages)
        for i, f in enumerate(sorted(fuelbeds, key=lambda fb: (-fb['pct'], fb['fccs_id']) )):
            truncated_fuelbeds.append(f)
            total_pct += f['pct']

            # if either treshold is None or 0, then don't truncate
            # by that that criterion
            if ((self.percentage_threshold and total_pct >= self.percentage_threshold)
                    or (self.count_threshold and i+1 >= self.count_threshold)):
                break

        # Note: we'll run adjust percentages even if nothing was truncated
        # in case percentages of initial set of fuelbeds don't add up to 100
        # (which should really never happen)

        return {
            "fuelbeds": self._adjust_percentages(truncated_fuelbeds),
            "fuelbeds_total_accounted_for_pct": total_pct
        }

    def _adjust_percentages(self, fuelbeds):
        total_pct = sum([fb['pct'] for fb in fuelbeds])

        if total_pct != 100.0:
            for fb in fuelbeds:
                # divide by total_pct before multiplying by 100 to avoid
                # rounding errors
                fb['pct'] = (fb['pct'] / total_pct) * 100.0
        # else, no adjustment necessary

        # return for convenience
        return fuelbeds
