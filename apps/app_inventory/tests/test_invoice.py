"""
The Invoice model has been removed.
Operation.amount is the authoritative total (sum of item quantity × unit_price
written at creation time); operation.effective_amount includes post-creation
adjustments.  No separate Invoice tests are needed.
"""
