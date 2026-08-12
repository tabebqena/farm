# TODO

[x] Fix the stock detail view, current state is mixed stock & stock history view, the stock detail view should show what is currenly in the stock with useful links, search & pagination.
The stock history should be able to answer the question "Where is my product went?" or "Why am I seeing product that I never buy".


[ ] On the sale operation that occurs between 2 entities that are internal entity, the product should be remoced from the seller stock stock, also, it should appear (Another line resembling the same product) in the buyer stock.
The reverse also for the purchase.
What will be the effect, Is there is any regression ?

Plan created.


[ ] The world entity can work as a vendor & a client , but with conditions, the operation should be fully payed & the user will never be able to reverse the paymenttransaction alone. if he need he should reverse the whole operation.

Status: Plan created , implementation popstponed.

[x] The current state allow repayment of a loan that have no payment transaction, this should be fixed. the non reversed/reversable repayment transactions sum shouldn't exceed the payment transaction sum.