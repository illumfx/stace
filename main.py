import os
import time
import secrets
import random
import string
import re
import undetected_chromedriver as uc

from imbox import Imbox
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

load_dotenv()


EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
PASSWORD_GENERATION_CHARS = string.ascii_letters + string.digits + string.punctuation
PASSWORD_LENGTH = 16

ACCOUNT_CREATION_PAGE = "https://store.steampowered.com/join"

def create_driver(chrome_path: str = "/usr/bin/chromium", driver_path: str = "/tmp/chromedriver"):
    """Create and return an undetected-chromedriver instance.

    Keeps driver creation out of module import so the module is safe to import
    in other contexts (tests, linters, etc.).
    """
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
    )

    return uc.Chrome(options=options, browser_executable_path=chrome_path, driver_executable_path=driver_path)

def get_steam_verification_link(sender: str, sent_to: str):
    steam_url_pattern = r'https://store\.steampowered\.com/account/newaccountverification\?[\w\?&=%-]+'

    while True:
        try:
            with Imbox(EMAIL_HOST, username=EMAIL_USER, password=EMAIL_PASSWORD, ssl=True) as imbox:
                # Get messages from Steam
                messages = imbox.messages(sent_from=sender)
                
                for uid, message in messages:
                    # Check recipient
                    recipients = [addr['email'].lower() for addr in message.sent_to]
                    if sent_to.lower() in recipients:
                        
                        body_content = ""
                        if message.body['plain']:
                            body_content += "".join(message.body['plain'])
                        if message.body['html']:
                            body_content += "".join(message.body['html'])
                        
                        match = re.search(steam_url_pattern, body_content)
                        if match:
                            verification_url = match.group(0)
                            print(f"✅ Found Link: {verification_url}")
                            
                            # --- DELETE THE EMAIL ---
                            imbox.delete(uid)
                            print(f"🗑️ Email {uid} deleted from server.")
                            
                            return verification_url
                            
            print("Link not found yet. Checking again...")
        except Exception as e:
            print(f"Mail Error: {e}")
            
        time.sleep(5)

def proceed_until_verification(email: str, driver):
    driver.get(ACCOUNT_CREATION_PAGE)
    wait = WebDriverWait(driver, 15)
    
    # --- FIX: Handle Cookie Popup ---
    try:
        # Wait a moment for the popup to potentially appear
        cookie_reject_btn = wait.until(EC.element_to_be_clickable((By.ID, "rejectAllButton")))
        cookie_reject_btn.click()
        print("✅ Cookie banner dismissed.")
    except Exception:
        # If it doesn't appear, just move on
        print("ℹ️ No cookie banner detected.")
    
    # Fill email fields
    wait.until(EC.presence_of_element_located((By.ID, "email"))).send_keys(email)
    driver.find_element(By.ID, "reenter_email").send_keys(email)
    driver.find_element(By.ID, "i_agree_check").click()

    # --- 1. Click the Checkbox ---
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.XPATH, "//iframe[contains(@title, 'checkbox')]")))
    checkbox = wait.until(EC.element_to_be_clickable((By.ID, "checkbox")))
    driver.execute_script("arguments[0].click();", checkbox)
    driver.switch_to.default_content()

    # --- 2. The Wait-for-Solve Logic ---
    print("Waiting for captcha to be fully solved...")
    
    # We check the hidden hCaptcha response field. 
    # It only gets a value once the captcha is solved (either auto-checked or image-solved).
    while True:
        # Check if the image challenge is currently blocking the screen
        challenge_frames = driver.find_elements(By.XPATH, "//iframe[contains(@title, 'content of the hCaptcha challenge')]")
        is_challenging = any(f.is_displayed() for f in challenge_frames)
        
        # Check if we have a success token yet
        # hCaptcha stores the result in a hidden textarea with name="h-captcha-response"
        token = driver.execute_script("return document.getElementsByName('h-captcha-response')[0] ? document.getElementsByName('h-captcha-response')[0].value : '';")
        
        if token and not is_challenging:
            print("✅ Captcha token detected and no challenge active. Proceeding...")
            break
        
        if is_challenging:
            print("🕒 Challenge active... awaiting user input.")
        
        time.sleep(2)

    # --- 3. Finalize Step ---
    driver.find_element(By.ID, "createAccountButton").click()
    
    # Wait for the age confirmation modal
    try:
        over_age_btn = wait.until(EC.element_to_be_clickable((By.ID, "overAgeButton")))
        over_age_btn.click()
    except Exception as e:
        print("Could not find OverAge button. Steam might have flagged the session.")
        
def finalize_registration(username: str, password: str, driver) -> bool:
    wait = WebDriverWait(driver, 15)
    
    while True:
        print(f"Attempting registration with User: {username}")
        
        # 1. Wait for fields to be visible
        try:
            account_input = wait.until(EC.visibility_of_element_located((By.ID, "accountname")))
            password_input = driver.find_element(By.ID, "password")
            reenter_password_input = driver.find_element(By.ID, "reenter_password")
        except Exception as e:
            print(f"❌ Could not find input fields: {e}")
            return False

        # 2. Clear and fill
        account_input.clear()
        account_input.send_keys(username)
        time.sleep(random.uniform(0.5, 1.5))  # Mimic human typing delay
        password_input.clear()
        password_input.send_keys(password)
        time.sleep(random.uniform(0.5, 1.5))  # Mimic human typing delay
        reenter_password_input.clear()
        reenter_password_input.send_keys(password)
        time.sleep(random.uniform(0.5, 1.5))  # Mimic human typing delay

        # 3. Submit
        submit_btn = driver.find_element(By.ID, "createAccountButton")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        # 4. Wait for either an Error OR Success (page transition)
        time.sleep(3) 
        
        # Use find_elements to avoid "NoSuchElementException"
        errors = driver.find_elements(By.ID, "error_display")
        
        if errors and errors[0].is_displayed() and len(errors[0].text.strip()) > 0:
            error_text = errors[0].text
            print(f"❌ Steam Error: {error_text}")
            
            # Check if we should retry
            if any(msg in error_text.lower() for msg in ["account name", "password", "available"]):
                print("🔄 Regenerating credentials and retrying...")
                username = generate_username()
                password = generate_password()
                continue 
            else:
                return False
        
        # 5. Check for Success
        # If the accountname input is gone, or we see a success message/redirect
        if len(driver.find_elements(By.ID, "accountname")) == 0:
            print(f"✅ Account successfully created: {username}")
            return True
        
        # Fallback: if no error is shown but we are still on the same page,
        # Steam might be lagging. Wait a bit longer.
        print("Waiting for response...")
        time.sleep(2)
    

def generate_password(length: int = PASSWORD_LENGTH) -> str:
    """Generate a password suitable for Steam:

    - Ensures minimum length (>=8)
    - Uses a restricted, safe punctuation set to avoid characters Steam commonly rejects
    - Guarantees at least one letter and one digit
    """
    if length < 8:
        length = 8

    letters = string.ascii_letters
    digits = string.digits
    # Keep punctuation conservative: avoid quotes, backslashes, angle brackets, spaces, etc.
    safe_punct = "!@#$%&*-_+=."

    # Ensure at least one letter and one digit
    pwd_chars = [secrets.choice(letters), secrets.choice(digits), secrets.choice(safe_punct)]

    all_chars = letters + digits + safe_punct
    while len(pwd_chars) < length:
        pwd_chars.append(secrets.choice(all_chars))

    # Shuffle to avoid predictable placement
    secrets.SystemRandom().shuffle(pwd_chars)
    return "".join(pwd_chars)


def generate_username():
    directory_path = os.path.dirname(__file__)
    adjectives, nouns = [], []
    with open(os.path.join(directory_path, "adjectives.txt"), "r") as file_adjective:
        with open(os.path.join(directory_path, "nouns.txt"), "r") as file_noun:
            for line in file_adjective:
                adjectives.append(line.strip())
            for line in file_noun:
                nouns.append(line.strip())

    # Fallbacks if wordlists are missing or empty
    if not adjectives:
        adjectives = ["quick", "silent", "brave", "curious"]
    if not nouns:
        nouns = ["fox", "river", "lion", "stone"]

    adjective = secrets.choice(adjectives).capitalize()
    noun = secrets.choice(nouns).capitalize()
    nums = "".join(str(random.randrange(10)) for _ in range(6))

    return adjective + noun + nums

def generate_random_email():
    # Generates email using ALIAS_FORMAT env var with random placeholder
    alias_format = os.environ.get("ALIAS_FORMAT", "test+[PLACEHOLDER]@example.com")
    random_suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    return alias_format.replace("[PLACEHOLDER]", random_suffix)


if __name__ == "__main__":
    # 1. Initialize data
    current_email = generate_random_email()
    password, username = generate_password(), generate_username()
    print(f"Target Email: {current_email}")
    print(f"User: {username} | Pass: {password}")

    driver = None
    try:
        # 2. Create driver and start the registration process
        driver = create_driver()
        proceed_until_verification(current_email, driver)

        # 3. Fetch the link from email (and delete it)
        verification_link = get_steam_verification_link("noreply@steampowered.com", current_email)
        
        # 4. Open verification tab
        driver.switch_to.new_window('tab')
        driver.get(verification_link)
        time.sleep(5)  # Let Steam process the verification
        driver.close()
        
        # 5. Finalize registration on the original tab
        driver.switch_to.window(driver.window_handles[0])
        success = finalize_registration(username, password, driver)
        
        if success:
            with open("accounts.txt", "a") as f:
                f.write(f"{datetime.now()}: {current_email} | {username} | {password}\n")
            print("💾 Account details saved to accounts.txt")

    except Exception as e:
        print(f"🚨 Critical Script Error: {e}")
    finally:
        # This runs NO MATTER WHAT (error or success)
        print("🧹 Cleaning up: Closing browser...")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
