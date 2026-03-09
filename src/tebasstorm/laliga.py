def screen_capture_loop(region):
    while True:
        screenshot = pyautogui.screenshot(region=region)
        
