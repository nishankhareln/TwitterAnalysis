import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
from openai import OpenAI

# TwitterScraper Class Definition
class TwitterScraper:
    def __init__(self, url, username, openai_api_key, tweet_limit=50, scroll_pause_time=2, scroll_count=15):
        self.url = url
        self.username = f"@{username}"  # Username formatted with '@'
        self.tweet_limit = tweet_limit
        self.scroll_pause_time = scroll_pause_time
        self.scroll_count = scroll_count
        self.driver = webdriver.Chrome()
        self.tweet_texts = []
        self.tweet_ids = set()
        self.client = OpenAI(api_key=openai_api_key)

    def login(self, twitter_username, twitter_password):
        """Log in to Twitter to access full tweets for the profile."""
        self.driver.get("https://twitter.com/login")
        username_field = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "text")))
        username_field.send_keys(twitter_username)
        username_field.send_keys(Keys.RETURN)
        password_field = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.NAME, "password")))
        password_field.send_keys(twitter_password)
        password_field.send_keys(Keys.RETURN)
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='AppTabBar_Home_Link']")))

    def get_tweets(self):
        self.driver.get(self.url)
        for _ in range(self.scroll_count):
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            tweets = soup.find_all('span', {'class': 'css-1jxf684'})
            current_tweet = []
            for tweet in tweets:
                text = tweet.get_text(strip=True)
                if text == "·":
                    collect_tweet = True
                    continue
                if text == self.username:
                    if current_tweet:
                        full_tweet = " ".join(current_tweet).strip()
                        cleaned_tweet = re.sub(r'\b(\d+)(?:\s*[A-Za-z]*)?\s+\1\b.*', '', full_tweet)
                        tweet_id = hash(cleaned_tweet)
                        if tweet_id not in self.tweet_ids:
                            self.tweet_texts.append(cleaned_tweet)
                            self.tweet_ids.add(tweet_id)
                        current_tweet = []
                        if len(self.tweet_texts) >= self.tweet_limit:
                            break
                    continue
                current_tweet.append(text)
            if len(self.tweet_texts) >= self.tweet_limit:
                break
            self.driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(self.scroll_pause_time)
        self.driver.quit()
        return self.tweet_texts

    def analyze_tweets_with_gpt(self, tweets, model="gpt-4-turbo", response_language="English", analyze_type="main_topics"):
        tweet_content = "\n".join(tweets)
        if analyze_type == "main_topics":
            prompt = (f"This person, {self.username}, usually tweets about the following topics:\n"
                      f"{tweet_content}\n\n"
                      f"What are the main topics this person tweets about? Please respond in {response_language}.")
            instructions = f"Analyze the topics discussed in the tweets and respond in {response_language}."
        elif analyze_type == "aggressive_language":
            prompt = (f"Here is a list of tweets by {self.username}:\n"
                      f"{tweet_content}\n\n"
                      f"Please analyze if this person tends to use aggressive or offensive language in their tweets. "
                      f"Respond with your analysis in {response_language}.")
            instructions = f"Check if the tweets contain any aggressive or offensive language and respond in {response_language}."
        assistant = self.client.beta.assistants.create(name="TwitterTopicAnalyzer", instructions="Analyze user's tweets", model=model)
        thread = self.client.beta.threads.create()
        message = self.client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        run = self.client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant.id, instructions=instructions)
        if run.status == 'completed':
            messages = self.client.beta.threads.messages.list(thread_id=thread.id)
            response_text = next((msg.content[0].text.value for msg in messages if msg.role == 'assistant'), "No response from assistant")
            return response_text
        else:
            return f"Run status: {run.status}"

# Streamlit Application Interface
st.title("Twitter Profile Analyzer")
st.write("Analyze tweets from a public Twitter profile using OpenAI GPT models.")

# User Inputs
username = st.text_input("Twitter Handle (without @)", "")
tweet_limit = st.number_input("Tweet Limit", min_value=10, max_value=200, step=10, value=50)
twitter_username = st.text_input("Your Twitter Username")
twitter_password = st.text_input("Your Twitter Password", type="password")
response_language = st.selectbox("Response Language", ["English", "Turkish"])
analyze_types = st.multiselect("Analysis Type", ["main_topics", "aggressive_language"])
model = st.selectbox("Choose Model", ["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4", "gpt-4o", "gpt-4o-mini"])

# Construct profile URL and get OpenAI API Key from Streamlit Secrets
profile_url = f"https://x.com/{username}"
openai_api_key = st.secrets["OPENAI_API_KEY"]

# Compute scroll count based on tweet limit
scroll_count = tweet_limit // 4

# Run Analysis
if st.button("Analyze"):
    if not all([username, twitter_username, twitter_password]):
        st.error("Please fill out all required fields.")
    else:
        st.write("Logging into Twitter and fetching tweets...")
        scraper = TwitterScraper(url=profile_url, username=username, openai_api_key=openai_api_key, tweet_limit=tweet_limit, scroll_count=scroll_count)
        scraper.login(twitter_username, twitter_password)
        tweets = scraper.get_tweets()
        st.write(f"Fetched {len(tweets)} tweets.")

        # Display each selected analysis type
        for analyze_type in analyze_types:
            analysis = scraper.analyze_tweets_with_gpt(tweets, model=model, response_language=response_language, analyze_type=analyze_type)
            st.subheader(f"{analyze_type.capitalize()} Analysis")
            st.write(analysis)
