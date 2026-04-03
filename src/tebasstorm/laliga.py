import io
import re
import time
import logging
import datetime
import subprocess as sp

import cv2
import yaml
import numpy as np
import pandas as pd
import pyautogui
import pytesseract
from PIL import Image
import Levenshtein


logger = logging.getLogger(__name__)

def get_adb_screenshot():
    adb_command = ['adb', 'exec-out', 'screencap', '-p']
    screenshot_data = sp.check_output(adb_command)
    screenshot = Image.open(io.BytesIO(screenshot_data))
    return screenshot

def get_pyautogui_screenshot(region):
    screenshot = pyautogui.screenshot(region=region)
    return screenshot

class LaLigaFantasy:
    MARKET_OPERATION_STR = 'Market operation'
    MARKET_OPERATION_ID = 'MO'

    SHIELD_STR = 'Shield'
    SHIELD_ID = 'S'

    REWARD_STR = 'Reward'
    REWARD_ID = 'R'

    SHOW_MORE_STR = 'Show more'

    NEW_MEMBER_STR = 'New member'

    SCROLL_STEP = -2
    SKIP_TH = 0.70

    def __init__(self, settings_fn: str):
        self._signatures = set()
        with open(settings_fn, 'r') as fp:
            self._settings = yaml.safe_load(fp)
            self._settings['teams'] = set(self._settings['teams'])
        
    def check_team(self, team):
        if team in self._settings['teams']:
            return team

        best_dist, target_team = len(team), ''
        for team_bis in self._settings['teams']:
            cur_dist = Levenshtein.distance(team, team_bis)
            if cur_dist < best_dist:
                target_team = team_bis
                best_dist = cur_dist
        
        if not target_team:
            raise RuntimeError

        return target_team

    @classmethod
    def get_date_from_str(cls, dt: datetime.datetime, date_str: str):
        if '/' in date_str:
            day, month, year = date_str.split('/')
            day, month, year = int(day), int(month), int(year)
            date = datetime.date(year, month, day)
        else:
            date_int = int(re.sub(r'\D', '', date_str))
            dt_int = 100 * dt.hour + dt.minute
            if date_int < dt_int:
                date = datetime.date(dt.year, dt.month, dt.day)
            else:
                ddt = dt - datetime.timedelta(days=1)
                date = datetime.date(ddt.year, ddt.month, ddt.day)

        return date

    @classmethod
    def get_signature(cls, date, mo_type, team1, team2, player, amount):
        sig = f'{date} {mo_type} {team1} {team2} {player} {amount}'
        return sig
        
    def get_entities_from_mo_line(self, date_str: str, mo_str: str):
        SOLD_REF = ' has sold player '
        PURCHASED_REF = 'has purchased '
        if SOLD_REF in mo_str:
            mo_type = 'sold'
            TEAM1_REF = SOLD_REF
            PLAYER_REF = ' to '
        else:
            mo_type = 'purchased'
            TEAM1_REF = PURCHASED_REF
            PLAYER_REF = ' from '

        idx1 = mo_str.find(TEAM1_REF)
        team1 = mo_str[:idx1].strip()

        idx1 = (idx1 + len(TEAM1_REF))
        idx2 = mo_str.find(PLAYER_REF)
        player = mo_str[idx1:idx2].strip()

        FOR_REF = ' for '
        idx1 = idx2 + len(PLAYER_REF)
        idx2 = mo_str.rfind(FOR_REF)
        team2 = mo_str[idx1:idx2].strip()

        idx1 = idx2 + len(FOR_REF)
        amount = int(re.sub(r'\D', '', mo_str[idx1:]))
        
        date = self.get_date_from_str(datetime.datetime.now(), date_str)
        team1 = self.check_team(team1)
        team2 = self.check_team(team2)
        return date, mo_type, team1, team2, player, amount
    
    def scan(self, lines):
        for idx, line in enumerate(lines):
            if len(lines) * self.SKIP_TH < idx:
                break

            if self.MARKET_OPERATION_STR in line:
                try:
                    sig, entities = self.get_market_operation(idx, line, lines)
                except RuntimeError:
                    raise
                except:
                    if idx < len(lines) * 0.25:
                        continue

                if sig in self._signatures:
                    continue

                self._signatures |= {sig}
                yield entities

            elif self.REWARD_STR in line:
                print('Reward')
            elif self.SHIELD_STR in line:
                print('Shield')

    def get_market_operation(self, idx, line, lines):
        date_str = ''.join(line.split(' ')[2:])            
        mo_lines = [] 
        for mo_line in lines[(idx + 1):]:
            mo_lines.append(mo_line)
            if '€' in mo_line:
                break
        
        clean_price = mo_lines[-1].split(',')
        mo_lines[-1] = clean_price[0] + re.sub(r'[^\d€]', '', ''.join(clean_price[1:]))
        mo_str = ' '.join(mo_lines).strip()
        if not mo_str.endswith('€'):
            raise RuntimeError(f'Issue: {mo_str}')
        
        entities = self.get_entities_from_mo_line(date_str, mo_str)
        sig = self.get_signature(*entities)
        return sig, entities

    def screen_capture_loop(self, limit_capture_date=None, auto=True):
        columns = ('date', 'type', 'team1', 'team2', 'player', 'amount')
        trading = pd.DataFrame()

        while True:
            screenshot = get_adb_screenshot()
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            img = cv2.medianBlur(img, 3)

            _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY_INV)
            
            output = pytesseract.image_to_string(img)
            lines = output.split('\n')
            rows = tuple(self.scan(lines))
            
            ddf = pd.DataFrame(rows, columns=columns)
            trading = pd.concat([trading, ddf], ignore_index=True)
            
            print(trading)
            print('---')

            if self.SHOW_MORE_STR in ' '.join(lines):
                break

            if limit_capture_date:
                if trading['date'].min() < limit_capture_date:
                    break

            if auto:
                output = sp.check_output(['xdotool', 'search', '--classname', 'scrcpy', 'getwindowgeometry'])
                output_lines = output.decode('utf-8').split('\n')

                position_line = output_lines[1]
                idx = position_line.find(',')
                x_pos = int(position_line[:idx].split(' ')[-1])
                y_pos = int(position_line[(idx + 1):].split(' ')[0])

                geometry_line = output_lines[2]
                idx = geometry_line.find('x')
                x_size = int(geometry_line[:idx].split(' ')[-1])
                y_size = int(geometry_line[(idx + 1):])
                
                region = (x_pos, y_pos + 10, x_size, y_size - 100)
                xx = (x_pos + x_size) // 2
                yy = (y_pos + y_size) // 2
                (x_pos + x_size) // 2
                
                pyautogui.scroll(self.SCROLL_STEP, x=xx, y=yy)
            else:
                time.sleep(0.5)

        return trading
    
    @classmethod
    def merge_trading_datasets(cls, historical_df, partial_df):
        def row_signature(row):
            date = row['date']
            mo_type = row['type']
            team1 = row['team1']
            team2 = row['team2']
            player = row['player']
            amount = row['amount']

            return cls.get_signature(date, mo_type, team1, team2, player, amount)
        
        ###
        historical_df['sig'] = pd.Series(row_signature(row) for _, row in historical_df.iterrows())
        partial_df['sig'] = pd.Series(row_signature(row) for _, row in partial_df.iterrows())

        ddf = partial_df[~(partial_df['sig'].isin(historical_df['sig']))]
        historical_df = pd.concat([ddf, historical_df], ignore_index=True)
        historical_df.drop(columns='sig', inplace=True)

        return historical_df
        