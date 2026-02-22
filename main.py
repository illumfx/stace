import os
import time
import secrets
import random
import string
import re
from datetime import datetime
import undetected_chromedriver as uc
from imbox import Imbox
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
import click
from colorama import init as colorama_init, Fore, Style

load_dotenv()

# Initialize colorama for colored console output
colorama_init(autoreset=True)


def info(msg: str):
    print(f"{Fore.CYAN}{msg}{Style.RESET_ALL}")


def success(msg: str):
    print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}")


def warn(msg: str):
    print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}")


def error(msg: str):
    print(f"{Fore.RED}{msg}{Style.RESET_ALL}")


EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
PASSWORD_GENERATION_CHARS = string.ascii_letters + string.digits + string.punctuation
PASSWORD_LENGTH = os.environ.get("PASSWORD_LENGTH", 16)  # Default to 16 if not set

ACCOUNT_CREATION_PAGE = "https://store.steampowered.com/join"


def create_driver(
    chrome_path: str = "/usr/bin/chromium", driver_path: str = "/tmp/chromedriver"
):
    """Create and return an undetected-chromedriver instance.

    Keeps driver creation out of module import so the module is safe to import
    in other contexts (tests, linters, etc.).
    """
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
    )

    return uc.Chrome(
        options=options,
        browser_executable_path=chrome_path,
        driver_executable_path=driver_path,
    )


def run_once(driver, password_length: int) -> bool:
    """Run the full registration flow once using an existing `driver`.

    Returns True on success. This function does NOT create or quit the driver;
    driver lifecycle is managed by the caller.
    """
    current_email = generate_random_email()
    password = generate_password(password_length)
    username = generate_username()

    info(f"Target Email: {current_email}")
    info(f"User: {username} | Pass: {password}")

    # Start the flow using provided driver
    proceed_until_verification(current_email, driver)

    verification_link = get_steam_verification_link(
        "noreply@steampowered.com", current_email
    )

    driver.switch_to.new_window("tab")
    driver.get(verification_link)
    time.sleep(5)
    driver.close()

    driver.switch_to.window(driver.window_handles[0])
    success_flag = finalize_registration(username, password, driver)

    if success_flag:
        with open("accounts.txt", "a") as f:
            f.write(f"{datetime.now()}: {current_email} | {username} | {password}\n")
        success("💾 Account details saved to accounts.txt")
        return True

    return False


def get_steam_verification_link(sender: str, sent_to: str):
    steam_url_pattern = (
        r"https://store\.steampowered\.com/account/newaccountverification\?[\w\?&=%-]+"
    )

    while True:
        try:
            with Imbox(
                EMAIL_HOST, username=EMAIL_USER, password=EMAIL_PASSWORD, ssl=True
            ) as imbox:
                # Get messages from Steam
                messages = imbox.messages(sent_from=sender)

                for uid, message in messages:
                    # Check recipient
                    recipients = [addr["email"].lower() for addr in message.sent_to]
                    if sent_to.lower() in recipients:

                        body_content = ""
                        if message.body["plain"]:
                            body_content += "".join(message.body["plain"])
                        if message.body["html"]:
                            body_content += "".join(message.body["html"])

                        match = re.search(steam_url_pattern, body_content)
                        if match:
                            verification_url = match.group(0)
                            success(f"✅ Found Link: {verification_url}")

                            # --- DELETE THE EMAIL ---
                            imbox.delete(uid)
                            info(f"🗑️ Email {uid} deleted from server.")

                            return verification_url

            info("Link not found yet. Checking again...")
        except Exception as e:
            error(f"Mail Error: {e}")

        time.sleep(5)


def proceed_until_verification(email: str, driver):
    driver.get(ACCOUNT_CREATION_PAGE)
    wait = WebDriverWait(driver, 15)

    # --- FIX: Handle Cookie Popup ---
    try:
        # Wait a moment for the popup to potentially appear
        cookie_reject_btn = wait.until(
            EC.element_to_be_clickable((By.ID, "rejectAllButton"))
        )
        cookie_reject_btn.click()
        success("✅ Cookie banner dismissed.")
    except Exception:
        # If it doesn't appear, just move on
        info("ℹ️ No cookie banner detected.")

    # Fill email fields
    wait.until(EC.presence_of_element_located((By.ID, "email"))).send_keys(email)
    driver.find_element(By.ID, "reenter_email").send_keys(email)
    driver.find_element(By.ID, "i_agree_check").click()

    # --- 1. Click the Checkbox ---
    wait.until(
        EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, "//iframe[contains(@title, 'checkbox')]")
        )
    )
    checkbox = wait.until(EC.element_to_be_clickable((By.ID, "checkbox")))
    driver.execute_script("arguments[0].click();", checkbox)
    driver.switch_to.default_content()

    # --- 2. The Wait-for-Solve Logic ---
    info("Waiting for captcha to be fully solved...")

    # We check the hidden hCaptcha response field.
    # It only gets a value once the captcha is solved (either auto-checked or image-solved).
    while True:
        # Check if the image challenge is currently blocking the screen
        challenge_frames = driver.find_elements(
            By.XPATH, "//iframe[contains(@title, 'content of the hCaptcha challenge')]"
        )
        is_challenging = any(f.is_displayed() for f in challenge_frames)

        # Check if we have a success token yet
        # hCaptcha stores the result in a hidden textarea with name="h-captcha-response"
        token = driver.execute_script(
            "return document.getElementsByName('h-captcha-response')[0] ? document.getElementsByName('h-captcha-response')[0].value : '';"
        )

        if token and not is_challenging:
            success("✅ Captcha token detected and no challenge active. Proceeding...")
            break

        if is_challenging:
            warn("🕒 Challenge active... awaiting user input.")

        time.sleep(2)

    # --- 3. Finalize Step ---
    driver.find_element(By.ID, "createAccountButton").click()

    # Wait for the age confirmation modal
    try:
        over_age_btn = wait.until(EC.element_to_be_clickable((By.ID, "overAgeButton")))
        over_age_btn.click()
    except Exception as e:
        warn("Could not find OverAge button. Steam might have flagged the session.")


def finalize_registration(username: str, password: str, driver) -> bool:
    wait = WebDriverWait(driver, 15)

    while True:
        info(f"Attempting registration with User: {username}")

        # 1. Wait for fields to be visible
        try:
            account_input = wait.until(
                EC.visibility_of_element_located((By.ID, "accountname"))
            )
            password_input = driver.find_element(By.ID, "password")
            reenter_password_input = driver.find_element(By.ID, "reenter_password")
        except Exception as e:
            error(f"❌ Could not find input fields: {e}")
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
            error(f"❌ Steam Error: {error_text}")

            # Check if we should retry
            if any(
                msg in error_text.lower()
                for msg in ["account name", "password", "available"]
            ):
                warn("🔄 Regenerating credentials and retrying...")
                username = generate_username()
                password = generate_password()
                continue
            else:
                return False

        # 5. Check for Success
        # If the accountname input is gone, or we see a success message/redirect
        if len(driver.find_elements(By.ID, "accountname")) == 0:
            success(f"✅ Account successfully created: {username}")
            return True

        # Fallback: if no error is shown but we are still on the same page,
        # Steam might be lagging. Wait a bit longer.
        info("Waiting for response...")
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
    pwd_chars = [
        secrets.choice(letters),
        secrets.choice(digits),
        secrets.choice(safe_punct),
    ]

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
    random_suffix = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8)
    )
    return alias_format.replace("[PLACEHOLDER]", random_suffix)


@click.command()
@click.option("--amount", default=1, help="Number of accounts to create in this run")
@click.option(
    "--chrome-path", default="/usr/bin/chromium", help="Path to chromium binary"
)
@click.option("--driver-path", default="/tmp/chromedriver", help="Path to chromedriver")
@click.option(
    "--alias-format",
    default=os.environ.get("ALIAS_FORMAT", "test+[PLACEHOLDER]@example.com"),
    help="Alias format for generated emails (must contain [PLACEHOLDER])",
)
@click.option(
    "--password-length",
    default=int(os.environ.get("PASSWORD_LENGTH", PASSWORD_LENGTH)),
    help="Length of generated passwords",
)
@click.option(
    "--retries",
    default=2,
    help="Number of times to retry on 'invalid session id' errors",
)
def main(amount, chrome_path, driver_path, alias_format, password_length, retries):
    """Run stace from the command line."""
    # propagate alias format into env for generate_random_email
    os.environ["ALIAS_FORMAT"] = alias_format
    driver = None
    try:
        driver = create_driver(chrome_path, driver_path)

        for i in range(amount):
            info(f"\n=== Starting account creation #{i+1} of {amount} ===")
            attempt = 0
            while attempt <= retries:
                try:
                    success_run = run_once(driver, password_length)
                    if success_run:
                        # success for this account, move on to next
                        break
                    else:
                        warn(
                            "Registration flow completed but account creation failed for this account."
                        )
                        break
                except Exception as e:
                    msg = str(e).lower()
                    # Retry for invalid session id / session deleted errors
                    if (
                        "invalid session id" in msg
                        or "session deleted" in msg
                        or "chrome not reachable" in msg
                    ):
                        attempt += 1
                        warn(
                            f"Browser session error detected: {e} — recreating driver and retrying ({attempt}/{retries})..."
                        )
                        # try to recreate driver before retrying
                        try:
                            if driver:
                                driver.quit()
                        except Exception:
                            pass
                        driver = create_driver(chrome_path, driver_path)
                        time.sleep(2)
                        continue
                    else:
                        error(f"🚨 Critical Script Error: {e}")
                        raise
        # end for
    finally:
        info("🧹 Cleaning up: Closing browser...")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
