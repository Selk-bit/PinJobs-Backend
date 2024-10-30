# Constants for XPaths and other values
ANCHORS_XPATH = "//a[contains(@href, '/jobs/view')]"
MODAL_DISMISS_XPATH = "//button[contains(@data-tracking-control-name, 'public_jobs_contextual-sign-in-modal_modal_dismiss')]"
TITLE_XPATH = "//h2[contains(@class, 'top-card-layout__title')]"
DESCRIPTION_XPATH = "//div[contains(@class, 'description__text')]"
SALARY_XPATH = "//div[contains(@class, 'compensation__salary')]"
COMPANY_XPATH = "//a[contains(@class, 'topcard__org-name-link')]"
POST_DATE_XPATH = ".//time"
LOCATION_XPATH = "//span[contains(@class, 'topcard__flavor topcard__flavor--bullet')]"
SIGN_IN_BUTTON_XPATH = "//a[contains(@class, 'sign-in-form__sign-in-cta')]"
SUBMIT_BUTTON_XPATH = "//input[contains(@class, 'join-form__form-body-submit-button')]"
USERNAME_INPUT_XPATH = "//input[@id='email-or-phone']"
POPULAR_WEBSITES = [
    "https://www.google.com",
    "https://www.wikipedia.org",
    "https://www.youtube.com",
    "https://www.amazon.com",
    "https://www.facebook.com",
    "https://www.twitter.com",
    "https://www.instagram.com",
    "https://www.reddit.com",
    "https://www.bbc.com",
]