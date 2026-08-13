# TODO

[x] Fix the stock detail view, current state is mixed stock & stock history view, the stock detail view should show what is currenly in the stock with useful links, search & pagination.
The stock history should be able to answer the question "Where is my product went?" or "Why am I seeing product that I never buy".


[ ] On the sale operation that occurs between 2 entities that are internal entity, the product should be remoced from the seller stock stock, also, it should appear (Another line resembling the same product) in the buyer stock.
The reverse also for the purchase.
What will be the effect, Is there is any regression ?

Plan created.


[ ] The world entity can work as a vendor & a client , but with conditions, the operation should be fully payed & the user will never be able to reverse the paymenttransaction alone. if he need he should reverse the whole operation.
Why we need?
The user may need to create pur/sale with entity that is not in the database, and this entity is not a regular one that makes a lot of operations, instead of forcing him to create an entity for each rarley appearing persons, we want to allow him to register the opertaion against world but we should avoid mixing the clients / vendors funds / payables / recivable , so if the user want to register a n opertation against a world, it should be one-shot like.

Status: Plan created , implementation popstponed.

[x] The current state allow repayment of a loan that have no payment transaction, this should be fixed. the non reversed/reversable repayment transactions sum shouldn't exceed the payment transaction sum.

