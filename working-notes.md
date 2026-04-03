# Working Notes

## Current Goal
Implementing Fund.balance as a computed property from transactions

## Status: IN PROGRESS
- [x] Fund model created
- [x] Transaction model created  
- [ ] Fund.balance property — next file: fund/models.py line 47
- [ ] Sale URL mapping missing from get_canonical_type()

## Next Step (EXACTLY what to do when returning)
Go to fund/models.py and add a balance property that sums
Transaction.amount where direction='in' minus direction='out'

## Known Bugs (don't forget)
- reversal_alert.html line 12: elif should check is_reversal not is_reversed
- app_adjustment AppConfig.name is wrong

## Blocked On
Nothing currently