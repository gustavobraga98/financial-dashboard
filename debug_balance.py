import pandas as pd
from datetime import datetime
from frontend.api_client import ApiClient

api = ApiClient()
txs = api.get_transactions()
crs = api.get_credits()
accs = api.get_accounts()

df_tx = pd.DataFrame(txs)
df_cr = pd.DataFrame(crs)

for col in ['account_id', 'description', 'amount', 'type', 'category', 'date']:
    if col not in df_tx.columns: df_tx[col] = None
for col in ['card_alias', 'description', 'amount', 'type', 'category', 'date']:
    if col not in df_cr.columns: df_cr[col] = None

if not df_tx.empty:
    df_tx['source'] = 'Conta'
    df_tx['date'] = pd.to_datetime(df_tx['date'])
if not df_cr.empty:
    df_cr['source'] = 'Cartão'
    df_cr['date'] = pd.to_datetime(df_cr['date'])
    
all_history = pd.concat([df_tx, df_cr], ignore_index=True)
if not all_history.empty:
    all_history = all_history.sort_values('date', ascending=False)

total_initial = sum(acc['initial_balance'] for acc in accs)
global_ref_date = max(pd.to_datetime(acc['initial_balance_date']).date() for acc in accs) if accs else datetime.now().date()

adj_inc, adj_exp = 0, 0
for _, tx in all_history.iterrows():
    if pd.isna(tx['date']): continue
    tx_date = tx['date'].date()
    if tx['source'] == 'Cartão':
        if tx_date > global_ref_date:
            if tx['type'] == 'income': adj_inc += tx['amount']
            else: adj_exp += tx['amount']
    else:
        acc = next((a for a in accs if a['id'] == tx['account_id']), None)
        if acc:
            acc_ref_date = pd.to_datetime(acc['initial_balance_date']).date()
            if tx_date > acc_ref_date:
                if tx['type'] == 'income': adj_inc += tx['amount']
                else: adj_exp += tx['amount']

print(f"Total Initial: {total_initial}")
print(f"Global Ref Date: {global_ref_date}")
print(f"Adj Income: {adj_inc}")
print(f"Adj Expense: {adj_exp}")
print(f"Current Balance: {total_initial + adj_inc - adj_exp}")
