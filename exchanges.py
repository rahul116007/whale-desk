"""Known centralised-exchange hot wallets on Ethereum (public labels: Etherscan / Arkham name tags).

Tracked wallets rarely swap on DEXs; they move size by sending to or withdrawing from exchanges. A withdrawal from an
exchange into a tracked wallet is accumulation, a deposit to an exchange is distribution. Anything not listed here is
treated as a neutral transfer. Unmatched addresses cost nothing, a wrong entry would mislabel one counterparty, so only
well-known, long-lived hot wallets are listed.
"""

EXCHANGES = {
    # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance 17",
    "0x9696f59e4d72e237be84ffd425dcad154bf96976": "Binance 18",
    "0x4976a4a02f38326660d17bf34b431dc6e2eb2327": "Binance 28",
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance 7",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance 28",
    # Coinbase
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase 10",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase 1",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 2",
    "0x3cd751e6b0078be393132286c442345e5dc49699": "Coinbase 3",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase 4",
    "0xeb2629a2734e272bcc07bda959863f316f4bd4cf": "Coinbase 5",
    "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase 6",
    "0x6b76f8b1e9e59913bfe758821887311ba1805cab": "Coinbase 11",
    # Kraken
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
    "0x0a869d79a7052c7f1b55a8ebabbea3421f0d11dd": "Kraken 2",
    "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken 3",
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken 4",
    "0xfa52274dd61e1643d2205169732f29114bc240b3": "Kraken 5",
    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX 2",
    "0x98ec059dc3adfbdd63429454aeb0c990fba4a128": "OKX 3",
    "0x5041ed759dd4afc3a72b8192c143f72f4724081a": "OKX 4",
    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
    "0xee5b5b923ffce93a870b3104b7ca09c3db80047a": "Bybit 2",
    # Gate.io
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe": "Gate.io",
    "0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c": "Gate.io 2",
    # Bitfinex
    "0x742d35cc6634c0532925a3b844bc454e4438f44e": "Bitfinex",
    "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa": "Bitfinex 2",
    "0x77134cbc06cb00b66f4c7e623d5fdbf6777635ec": "Bitfinex 3",
    # Crypto.com
    "0x6262998ced04146fa42253a5c0af90ca02dfd2a3": "Crypto.com",
    "0x46340b20830761efd32832a74d7169b29feb9758": "Crypto.com 2",
    # KuCoin
    "0x2b5634c42055806a59e9107ed44d43c426e58258": "KuCoin",
    "0x689c56aef474df92d44a1b70850f808488f9769c": "KuCoin 2",
    "0xd6216fc19db775df9774a6e33526131da7d19a2c": "KuCoin 6",
    # HTX (Huobi)
    "0xab5c66752a9e8167967685f1450532fb96d5d24f": "HTX",
    "0xe93381fb4c4f14bda253907b18fad305d799241a": "HTX 2",
    "0x5c985e89dde482efe97ea9f1950ad149eb73829b": "HTX 5",
    # Bitget / MEXC / Robinhood / Gemini
    "0x0639556f03714a74a5feeaf5736a4a64ff70d206": "Bitget",
    "0x3cc936b795a188f0e246cbb2d74c5bd190aecf18": "MEXC",
    "0x40b38765696e3d5d8d9d834d8aad4bb6e418e489": "Robinhood",
    "0x5f65f7b609678448494de4c87521cdf6cef1e932": "Gemini 4",
    "0xd24400ae8bfebb18ca49be86258a3c749cf46853": "Gemini 3",
}

def short(addr):
    return addr[:6] + "…" + addr[-4:] if addr else "?"

EXCHANGES_SHORT = {short(a): n for a, n in EXCHANGES.items()}   # trades.csv notes only carry the short form

def name_for(addr):
    """Exchange name for a full or short address, else None."""
    if not addr: return None
    a = addr.lower()
    return EXCHANGES.get(a) or EXCHANGES_SHORT.get(addr) or EXCHANGES_SHORT.get(short(a))

def in_note(note):
    """Exchange name mentioned in a trades.csv note ('from 0x28c6…1d60', 'sent to Binance 14'), else None."""
    if not note: return None
    for tok in note.replace("(", " ").replace(")", " ").split():
        n = name_for(tok)
        if n: return n
    for n in set(EXCHANGES.values()):
        if n in note: return n
    return None
