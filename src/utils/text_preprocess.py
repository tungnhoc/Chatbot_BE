import re
# import nltk
# from nltk.corpus import stopwords
# from nltk.stem import PorterStemmer

# for resource in ["stopwords", "punkt", "punkt_tab"]:
#     try:
#         nltk.data.find(resource)
#     except LookupError:
#         nltk.download(resource)


def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text) 
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def remove_stopwords(text: str) -> str:
    # stop_words = set(stopwords.words('english'))
    # words = nltk.word_tokenize(text)
    # filtered = [word for word in words if word not in stop_words and len(word) > 2]
    return text


def stem_text(text: str) -> str:
    # stemmer = PorterStemmer()
    # words = nltk.word_tokenize(text)
    # stemmed = [stemmer.stem(word) for word in words]
    return text

def preprocess_text(text: str) -> str:
    cleaned = clean_text(text)
    no_stop = remove_stopwords(cleaned)
    stemmed = stem_text(no_stop)
    return stemmed

# if __name__ == "__main__":
#     sample_text = "This is a sample text with stopwords and noise!!! 123"
#     processed = preprocess_text(sample_text)
#     print(f"Processed: {processed}")