#!/usr/bin/env python3
"""Display the private first-run code locally; never accepts a password in argv."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from services.accounts import Accounts
store=Accounts(os.getenv('VLM_ACCOUNT_DIR','data/private'))
if store.initialized():
    print('Host account is already set up. Open /login to sign in.')
else:
    print('Open http://127.0.0.1:5000/setup and create your administrator account.')
    print('One-time setup code (keep private): '+store.setup_token)
