"""영한 뜻풀이(영어공부 카드) — original_lang/enko_dict.sqlite 를 찾아본다.

자료(tools/make_enko.py 가 만든다):
  bible   : 성경 영한 낱말장 — BSB ↔ 개역한글S 를 Strong 번호로 짝지어 성경 전체에서 센
            '이 영어 낱말이 성경에서 실제로 무엇으로 옮겨졌나'(covenant → 언약 162).
            BSB(CC0) · 개역한글(퍼블릭 도메인)에서 나와 배포에 제약이 없다.
  general : 일반 영한 뜻 — kengdic(https://github.com/garfieldnate/kengdic, MPL 2.0 / LGPL 중 선택)의
            한→영 항목을 영→한으로 뒤집은 것. 파일 info 표에 출처 · 라이선스를 적어 둔다.

찾기는 활용형을 원형으로 돌려(was → be, offerings → offering, cried → cry) 맞춘다.
"""
import json
import os
import re
import sqlite3
import threading

# 짝을 찾지 않는 영어 작은 낱말(구절 'My covenant' 에서 머리말은 covenant).
STOP = frozenset({
    'the', 'a', 'an', 'of', 'to', 'and', 'or', 'but', 'that', 'who', 'whom', 'which', 'in', 'for', 'with', 'by',
    'on', 'at', 'from', 'as', 'his', 'her', 'their', 'my', 'your', 'our', 'its', 'he', 'she', 'it', 'they', 'we',
    'you', 'i', 'me', 'him', 'them', 'us', 'will', 'shall', 'would', 'should', 'not', 'this', 'these', 'those',
    'so', 'then', 'there', 'into', 'up', 'out', 'upon', 'also', 'when', 'all', 'no', 'if', 'than', 'thy', 'thee',
    'thou', 'ye', 'unto', 'every', 'any', 'one',
})
# 불규칙 활용 → 원형(성경에 자주 나오는 것).
IRREGULAR = {
    'is': 'be', 'was': 'be', 'were': 'be', 'am': 'be', 'been': 'be', 'are': 'be', 'being': 'be',
    'had': 'have', 'has': 'have', 'said': 'say', 'did': 'do', 'does': 'do', 'done': 'do', 'came': 'come',
    'went': 'go', 'gone': 'go', 'goes': 'go', 'made': 'make', 'took': 'take', 'taken': 'take', 'gave': 'give',
    'given': 'give', 'brought': 'bring', 'sent': 'send', 'told': 'tell', 'became': 'become', 'men': 'man',
    'women': 'woman', 'children': 'child', 'feet': 'foot', 'teeth': 'tooth', 'oxen': 'ox', 'written': 'write',
    'wrote': 'write', 'saw': 'see', 'seen': 'see', 'found': 'find', 'spoke': 'speak', 'spoken': 'speak',
    'knew': 'know', 'known': 'know', 'stood': 'stand', 'sat': 'sit', 'heard': 'hear', 'left': 'leave',
    'kept': 'keep', 'fell': 'fall', 'fallen': 'fall', 'ate': 'eat', 'eaten': 'eat', 'began': 'begin',
    'begun': 'begin', 'built': 'build', 'struck': 'strike', 'rose': 'rise', 'risen': 'rise', 'led': 'lead',
    'fled': 'flee', 'slew': 'slay', 'slain': 'slay', 'burnt': 'burn', 'thought': 'think', 'sought': 'seek',
    'bore': 'bear', 'borne': 'bear', 'born': 'bear', 'drank': 'drink', 'drunk': 'drink', 'sang': 'sing',
    'sung': 'sing', 'gathered': 'gather', 'brethren': 'brother', 'lay': 'lie', 'lain': 'lie', 'fought': 'fight',
    'taught': 'teach', 'bought': 'buy', 'sold': 'sell', 'held': 'hold', 'met': 'meet', 'paid': 'pay',
    'laid': 'lay', 'won': 'win', 'swore': 'swear', 'sworn': 'swear', 'tore': 'tear', 'torn': 'tear',
    'wept': 'weep', 'slept': 'sleep', 'spent': 'spend', 'felt': 'feel', 'fed': 'feed', 'drew': 'draw',
    'drawn': 'draw', 'grew': 'grow', 'grown': 'grow', 'threw': 'throw', 'thrown': 'throw', 'flew': 'fly',
    'hid': 'hide', 'hidden': 'hide', 'rode': 'ride', 'ran': 'run', 'chose': 'choose', 'chosen': 'choose',
    'forgave': 'forgive', 'forgiven': 'forgive', 'forsook': 'forsake', 'forsaken': 'forsake', 'shook': 'shake',
    'shaken': 'shake', 'broke': 'break', 'broken': 'break', 'woke': 'wake', 'arose': 'arise', 'arisen': 'arise',
    'overcame': 'overcome', 'understood': 'understand', 'withheld': 'withhold', 'blew': 'blow', 'dug': 'dig',
    'hung': 'hang', 'shone': 'shine', 'stole': 'steal', 'stolen': 'steal', 'strove': 'strive', 'trod': 'tread',
    'wore': 'wear', 'worn': 'wear', 'lent': 'lend', 'meant': 'mean', 'dealt': 'deal', 'dwelt': 'dwell',
    'mice': 'mouse', 'lice': 'louse', 'geese': 'goose', 'better': 'good', 'best': 'good', 'worse': 'bad',
    'worst': 'bad', 'greater': 'great', 'greatest': 'great',
}


def lemmas(word):
    """영어 낱말 → 찾아볼 원형 후보(앞이 먼저).

    불규칙(was → be) → 복수(heavens → heaven, offerings → offering) → 낱말 그대로 → 과거(cried → cry)
    → 그 밖의 꼴(-ing · -er · -est · -ness · -ly).
    - 과거형을 낱말 뒤에 두는 것은 wicked · blessed · naked 처럼 -ed 로 끝나는 낱말을 깎지 않으려고
      (찾는 쪽이 사전에 있는 첫 후보를 쓰므로 cried 는 사전에 없어 cry 로 간다).
    - -ing 등을 맨 뒤에 두는 것은 offering · blessing 처럼 그 꼴 자체가 명사인 낱말을 동사로 깎지 않으려고.
    - 깎은 원형은 세 글자 이상만(died → 'di' 같은 찌꺼기 방지)."""
    w = (word or '').lower().strip("'’")
    if not w:
        return []
    first, past, late = [], [], []
    if w in IRREGULAR:
        first.append(IRREGULAR[w])
    if w.endswith("'s"):
        first.append(w[:-2])

    def add(bucket, base, dbl=False):
        if dbl and len(base) > 3 and base[-1] == base[-2] and base[-1] not in 'lsz':
            bucket.append(base[:-1])       # stopped → stop, bigger → big
        if len(base) >= 3:
            bucket.append(base)

    for suf, rep in (('ies', 'y'), ('ves', 'f'), ('ves', 'fe'), ('es', ''), ('s', '')):
        if not w.endswith(suf) or len(w) < len(suf) + 2:
            continue
        if suf == 's' and w.endswith(('ss', 'us', 'is', 'ous')):
            continue                       # righteous · grass · this 는 복수가 아니다
        add(first, w[:-len(suf)] + rep)
    for suf, rep in (('ied', 'y'), ('ed', ''), ('ed', 'e')):
        if w.endswith(suf) and len(w) >= len(suf) + 2:
            add(past, w[:-len(suf)] + rep, dbl=(suf == 'ed'))
    for suf, rep in (('ier', 'y'), ('iest', 'y'), ('ing', ''), ('ing', 'e'), ('est', ''), ('er', ''),
                     ('ness', ''), ('ly', '')):
        if w.endswith(suf) and len(w) >= len(suf) + 2:
            add(late, w[:-len(suf)] + rep, dbl=suf in ('ing', 'er', 'est'))
    seen, res = set(), []
    for x in first + [w] + past + late:
        if x and x not in seen:
            seen.add(x)
            res.append(x)
    return res


def content_words(phrase):
    """구절 → 내용어(작은 낱말 뺌), 뒤에서부터(영어 명사구는 머리말이 끝)."""
    ws = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'’]*", phrase or '')]
    return [w for w in reversed(ws) if w.strip("'’") not in STOP] or list(reversed(ws))


class EnKoDict:
    """enko_dict.sqlite 찾아보기. 파일이 없으면 available=False, lookup 은 None."""

    def __init__(self, path):
        self.path = path
        self._con = None
        self._lock = threading.Lock()
        self.info = {}
        if path and os.path.isfile(path):
            try:
                self._con = sqlite3.connect(f'file:{path}?mode=ro', uri=True, check_same_thread=False)
                self.info = dict(self._con.execute('SELECT name, value FROM info'))
            except sqlite3.Error:
                self._con = None

    @property
    def available(self):
        return self._con is not None

    def _get(self, table, word):
        with self._lock:
            row = self._con.execute(f'SELECT data FROM {table} WHERE word=?', (word,)).fetchone()
        return json.loads(row[0]) if row else None

    def lookup(self, phrase):
        """구절(영어공부 카드에서 누른 것) → {'query', 'word', 'bible': [[한국어, 횟수]…], 'general': [한국어…],
        'source'} 또는 None. 내용어를 뒤에서부터, 원형 후보 차례로 찾아 처음 걸리는 것."""
        if not self.available:
            return None
        for w in content_words(phrase):
            for lem in lemmas(w):
                bible = self._get('bible', lem)
                general = self._get('general', lem)
                if bible or general:
                    return {'query': w, 'word': lem, 'bible': bible or [], 'general': general or [],
                            'source': self.info.get('general_source', '')}
        return None
