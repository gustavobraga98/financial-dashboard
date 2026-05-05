# Database Setup Task

Define the SQLAlchemy models and database session for the financial dashboard.
We will use the sample file to get the structure right and make sure we cover all cases.
The sample file is the exact file format that the user will be sending to the system. But keep in mind that in the initial setup
we need to be able to provide a starting balance value. You can decide if it is better to be the first transaction or just a variable in the database. You may propose different solutions for the user to pick one. Make your proposal and justify it. After the initial balance, all the registered transactions will come from files exactly like the one here: /home/gustavo/Projects/financial-dashboard/sample_report.txt. This dashboard will manage a single bank account for now, but in the future we may want to manage multiple bank accounts, so try to keep it in mind for the design. 

For the credit management we will also keep track of the amount of payment that the user makes to the credit card, so we need to be able to distinguish between purchases made with debit and purchases made with credit. the credit file format is available here: /home/gustavo/Projects/financial-dashboard/credit.csv.

For the credit we also must register an alias for the card so we can properly manage the payments of the credit card. The user must inform that in the UI and then the request will be made with the file + the alias of the card that must be in the credit table. This alias is not required for the debit transactions.

## Objectives
- Configure SQLAlchemy with SQLite.
- Create models for `Transaction` (id, description, amount, type [expense/income], category, date).
- Create models for `Credit` (id, description, amount, type [expense/income], category, date).
- Implement a database session dependency for FastAPI.
- Create initial tables (Base.metadata.create_all).
