"""
nlp_engine.py — Kerala Tourism Chatbot NLP Engine
===================================================
ZERO EXTERNAL DEPENDENCIES — pure Python only.
Works without sklearn, fuzzywuzzy, or numpy.
"""

import json, re, math, random, os
from collections import Counter

DISTRICT_ENTITY_MAP = {
    "district_thiruvananthapuram": ["thiruvananthapuram","trivandrum","kovalam","varkala","padmanabhaswamy","napier museum","agasthyarkoodam","ponmudi","kuthiramalika","shanghumugham","neyyar"],
    "district_ernakulam": ["ernakulam","kochi","cochin","fort kochi","fort cochin","mattancherry","cherai","hill palace","wonderla","bolgatty","chinese fishing nets","jew town","vypeen","mangalavanam"],
    "district_thrissur": ["thrissur","trichur","thrissur pooram","athirappilly","guruvayur","kalamandalam","vadakkunnathan","snehatheeram","peechi","vazhachal","parambikulam","shakthan"],
    "district_palakkad": ["palakkad","palakad","palakkad fort","silent valley","malampuzha","nelliyampathy","pothundy","dhoni","kalpathy"],
    "district_munnar": ["munnar","eravikulam","mattupetty","top station","neelakurinji","attukal","nilgiri tahr","rajamala","lockhart","chinnakanal","rose garden"],
    "district_wayanad": ["wayanad","chembra","edakkal","pookode","soochipara","vythiri","kalpetta","banasura","thirunelli","muthanga","phantom rock"],
    "district_kozhikode": ["kozhikode","calicut","beypore","kappad","tusharagiri","mananchira","sweet street","sm street","elathur","pazhassiraja"],
    "district_kannur": ["kannur","cannanore","theyyam","st angelo","muzhappilangad","parassinikadavu","ezhimala","arakkal","meenkunnu","dharmadom"],
    "district_kasaragod": ["kasaragod","bekal","ananthapura","valiyaparamba","chandragiri","malik deenar","ranipuram","madhur","kappil","nileshwaram","hosdurg"],
    "district_alappuzha": ["alappuzha","alleppey","kettuvallam","vembanad","marari","nehru trophy","punnamada","kumarakom","arthunkal","chettikulangara","ambalappuzha","pathiramanal"],
    "district_kollam": ["kollam","quilon","ashtamudi","thirumullavaram","palaruvi","jatayu","thangassery","munroe island","alumkadavu","mayyanad","sasthamcotta"],
    "district_pathanamthitta": ["pathanamthitta","sabarimala","konni","gavi","aranmula","perunthenaruvi","pamba","kakki"],
    "district_kottayam": ["kottayam","thekkady","periyar","vagamon","illikkal","poonjar","ettumanoor","mundakayam"],
    "district_malappuram": ["malappuram","nilambur","kottakkunnu","kadalundi","tanur","tirur","thunchan","pandikkad"],
}

TOPIC_ENTITY_MAP = {
    "backwaters":    ["backwater","houseboat","kettuvallam","canal tour","lagoon","boat cruise","vembanad","backwater cruise","boat ride"],
    "beaches":       ["beach","seaside","seashore","sandy beach","coastal","sea shore","swim"],
    "hill_stations": ["hill station","mountain","highland","cool climate","misty","altitude","trekking","trek","hills"],
    "weather":       ["weather","climate","temperature","rain","monsoon","rainfall","season","when to visit","best time","best month"],
    "food":          ["food","cuisine","eat","dish","sadhya","restaurant","meal","breakfast","seafood","biriyani","halwa","appam","puttu","fish curry","what to eat"],
    "budget":        ["budget","cheap","affordable","cost","price","how much","expenses","low cost","economy","free"],
    "wildlife":      ["wildlife","safari","tiger","elephant","animals","jungle","forest","national park","bird watching","birds"],
    "ayurveda":      ["ayurveda","ayurvedic","massage","spa","wellness","panchakarma","herbal","treatment","rejuvenation"],
    "festivals":     ["festival","onam","pooram","boat race","vishu","biennale","pookalam","celebration"],
    "family_trip":   ["family trip","family vacation","kids","children","family package","family plan","family tour"],
    "honeymoon":     ["honeymoon","romantic","couple trip","anniversary","love","wedding trip","couple","romance"],
    "best_places":   ["best places","top places","must visit","famous places","popular places","tourist spots","where to go","suggest","recommend","places to visit"],
    "how_to_reach":  ["how to reach","how to go","flight","train","airport","bus route","transport","travel to","get to kerala"],
}

def _tokenize(text):
    return re.sub(r'[^a-z0-9\s]', ' ', text.lower()).split()

def _build_tfidf(corpus):
    tokenized = [_tokenize(d) for d in corpus]
    N = len(tokenized)
    df = Counter()
    for tokens in tokenized:
        for t in set(tokens):
            df[t] += 1
    idf = {t: math.log((N+1)/(freq+1))+1 for t,freq in df.items()}
    vectors = []
    for tokens in tokenized:
        tf = Counter(tokens)
        n = len(tokens) or 1
        vectors.append({t: (c/n)*idf[t] for t,c in tf.items() if t in idf})
    return idf, vectors

def _cosine(a, b):
    dot = sum(a.get(t,0)*v for t,v in b.items())
    na = math.sqrt(sum(v*v for v in a.values())) or 1e-9
    nb = math.sqrt(sum(v*v for v in b.values())) or 1e-9
    return dot/(na*nb)

def _levenshtein(a, b):
    if len(a)<len(b): return _levenshtein(b,a)
    if not b: return len(a)
    prev = list(range(len(b)+1))
    for i,ca in enumerate(a):
        curr=[i+1]
        for j,cb in enumerate(b):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(0 if ca==cb else 1)))
        prev=curr
    return prev[-1]

def _fuzzy(a, b):
    d = _levenshtein(a.lower(), b.lower())
    return round(100*(1-d/max(len(a),len(b),1)))


class KeralaBot:
    def __init__(self, data_path):
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.intents = data['intents']
        self.responses = {i['tag']: i['responses'] for i in self.intents}
        corpus, self.labels = [], []
        for intent in self.intents:
            for pattern in intent['patterns']:
                corpus.append(pattern)
                self.labels.append(intent['tag'])
        self.idf, self.doc_vectors = _build_tfidf(corpus)
        self._dist_kw = [(kw,tag) for tag,kws in DISTRICT_ENTITY_MAP.items() for kw in kws]
        print(f"[KeralaBot] Loaded {len(self.intents)} intents, {len(corpus)} patterns (pure-Python)")

    def _entity_detect(self, text):
        tl = text.lower().strip()
        for tag, kws in DISTRICT_ENTITY_MAP.items():
            for kw in kws:
                if kw in tl:
                    return tag, 0.99
        for topic, kws in TOPIC_ENTITY_MAP.items():
            for kw in kws:
                if kw in tl:
                    return topic, 0.95
        for word in tl.split():
            if len(word) < 4: continue
            best, btag = 0, None
            for kw, tag in self._dist_kw:
                s = _fuzzy(word, kw)
                if s > best: best, btag = s, tag
            if best >= 82:
                return btag, best/100.0
        return None, 0.0

    def _predict_tfidf(self, text):
        tokens = _tokenize(text)
        if not tokens: return 'unknown', 0.0
        n = len(tokens)
        tf = Counter(tokens)
        qvec = {t:(c/n)*self.idf[t] for t,c in tf.items() if t in self.idf}
        if not qvec: return 'unknown', 0.0
        best_score, best_label = 0.0, 'unknown'
        for dvec, label in zip(self.doc_vectors, self.labels):
            score = _cosine(qvec, dvec)
            if score > best_score:
                best_score, best_label = score, label
        return (best_label, best_score) if best_score >= 0.10 else ('unknown', best_score)

    def get_response(self, user_message):
        if not user_message or not user_message.strip():
            return {'response':"Please type a message! Ask me anything about Kerala 🌴",'intent':'empty','confidence':0.0}
        intent_tag, confidence = self._entity_detect(user_message)
        if intent_tag is None:
            intent_tag, confidence = self._predict_tfidf(user_message)
        possible = self.responses.get(intent_tag) or self.responses.get('unknown', [
            "I'm not sure about that. Try asking about Kerala places, districts, food, weather or travel tips! 🌴"
        ])
        return {'response': random.choice(possible), 'intent': intent_tag, 'confidence': round(confidence,3)}


_bot_instance = None

def get_bot_instance(data_path=None):
    global _bot_instance
    if _bot_instance is None:
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__),'..','data','chatbot_intents.json')
        _bot_instance = KeralaBot(data_path)
    return _bot_instance
