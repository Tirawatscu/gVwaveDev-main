from flask_migrate import Migrate
from mainwebbase import db, create_app

app = create_app()
migrate = Migrate(app, db)
