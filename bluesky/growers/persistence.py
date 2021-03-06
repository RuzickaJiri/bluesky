"""bluesky.growers.persistence"""

__author__ = "Joel Dubowy"

__version__ = "0.1.0"

import copy
import datetime

from afdatetime.parsing import parse as parse_dt

from bluesky.exceptions import BlueSkyConfigurationError
from bluesky.config import Config
from . import GrowerBase, to_date


DAYS_TO_PERSIST_NOT_INT = "'days_to_persist' must be a positive integer"

class Grower(GrowerBase):

    def __init__(self):
        super().__init__()

        # Note: set date to persist in grow(), since we need fires_manager
        # to set default to the run's 'today'

        # cast to int in case it was specified as string in config file or on
        # command line (really, no excuse for this, since you can use -I option)
        self._days_to_persist = int(self.config('days_to_persist'))
        if self._days_to_persist <= 0:
            raise BlueSkyConfigurationError(DAYS_TO_PERSIST_NOT_INT)

        self._truncate = self.config('truncate')

    def grow(self, fires_manager):

        self._date_to_persist = (to_date(self.config('date_to_persist'))
            or fires_manager.today().date())

        for fire in fires_manager.fires:
            with fires_manager.fire_failure_handler(fire):
                self._grow_fire(fire)

    def _grow_fire(self, fire):
        if not any([a.get('active_areas') for a in fire.get('activity', [])]):
            return

        # TODO: figure out how to actually specify the following
        if fire.get('type', 'wf').lower() == 'rx':
            self._fill_in_rx(fire)
        else:
            self._fill_in_wf(fire)

    def _fill_in_rx(self, fire):
        # do anything?
        pass

    def _fill_in_wf(self, fire):
        # activity will be in in chronological order, both the activity
        # collections as well as the active areas within each collection.
        # Active area windows will never span two days (since Spider
        # limits growth_window_length to some divisor of 24)

        # leave growth as is if case 1) (with or without truncation)
        # or if case 3) or 4) without truncation
        first_start = to_date(fire['activity'][0]['active_areas'][0]['start'])
        last_start = to_date(fire['activity'][-1]['active_areas'][-1]['start'])
        if (last_start < self._date_to_persist or
                (not self._truncate and last_start > self._date_to_persist)):
            return

        before_activity = []
        date_to_persist_activity = []
        for a in fire['activity']:
            a_start = to_date(a["active_areas"][0]['start'])
            if a_start < self._date_to_persist:
                before_activity.append(copy.deepcopy(a))
            elif a_start == self._date_to_persist:
                date_to_persist_activity.append(copy.deepcopy(a))
            else:
                # stop processing
                break

        fire['activity'] = (before_activity + date_to_persist_activity
            + self._persist(date_to_persist_activity))

    ONE_DAY = datetime.timedelta(days=1)

    def _persist(self, date_to_persist_activity):
        if not date_to_persist_activity:
            return []

        persisted_activity = []
        for i in range(self._days_to_persist):
            activity = copy.deepcopy(date_to_persist_activity)
            t_diff = (i + 1) * self.ONE_DAY
            for a in activity:
                for aa in a['active_areas']:
                    aa['start'] = parse_dt(aa['start']) + t_diff
                    aa['end'] = parse_dt(aa['end']) + t_diff
                    self._add_time_diff_to_keys(aa, t_diff, ('timeprofile',))
                    for l in aa.locations:
                        self._add_time_diff_to_keys(l, t_diff, ('plumerise',))

                persisted_activity.append(a)

        return persisted_activity

    def _add_time_diff_to_keys(self, d, t_diff, fields):
        # instantiate list from timeprofile's and plumerise's keys
        # to avoid unexpected behavior when popping and replacing
        # keys within for loop
        for f in fields:
            for k in list(d.get(f, {})):
                new_k = (parse_dt(k) + t_diff).strftime('%Y-%m-%dT%H:%M:%S')
                d[f][new_k] = d[f].pop(k)
