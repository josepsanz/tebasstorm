import io
import time
import subprocess as sp

import cv2
import numpy as np
import pandas as pd
import pyautogui
import pytesseract
from PIL import Image


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
        
    @classmethod
    def get_entities_from_mo_line(cls, date_str: str, mo_str: str):
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
        amount = mo_str[idx1:].replace(',', '').replace(' ', '').replace('€', '')
        return date_str, mo_type, team1, team2, player, amount
        
    @classmethod
    def get_market_operations_from_lines(cls, lines):
        for idx, line in enumerate(lines):
            if cls.MARKET_OPERATION_STR not in line:
                continue
            
            # MO
            date_str = ''.join(line.split(' ')[2:])            
            mo_lines = [] 
            for mo_line in lines[(idx + 1):]:
                mo_lines.append(mo_line)
                if '€' in mo_line:
                    break
            
            mo_str = ' '.join(mo_lines).strip()
            if mo_str.endswith('€'):
                entities = cls.get_entities_from_mo_line(date_str, mo_str)
                yield entities

    @classmethod
    def screen_capture_loop(cls):
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
            mo_lines = tuple(cls.get_market_operations_from_lines(lines))
            
            ddf = pd.DataFrame(mo_lines, columns=columns)
            trading = pd.concat([trading, ddf], ignore_index=True)
            
            print(trading)
            time.sleep(5)
            pyautogui.scroll(-1, x=xx, y=yy)


        return trading
        
