
# PawPal 🐾

PawPal is a web application designed to connect pet owners with caregivers who provide services such as pet sitting, walking, feeding, and drop-in visits.

The platform aims to simplify the process of finding reliable pet care, managing pet profiles, coordinating bookings, and connecting members of the pet-care community.

PawPal is being developed as a collaborative software engineering project.

## Technology Stack

- **Backend:** Python, Django
- **Frontend:** HTML, CSS, JavaScript
- **Database:** PostgreSQL
- **Cloud Infrastructure:** Amazon Web Services (AWS)
- **UI/UX Design:** Figma
- **Version Control:** Git and GitHub
- **Pillow** – Python image-processing library used with Django's `ImageField` to support profile photo uploads.

## Getting Started

### Prerequisites

Before setting up the project, make sure you have:

- Python installed
- Git installed
- A code editor such as Visual Studio Code

### 1. Clone the Repository

```bash
git clone -b develop https://github.com/gcivil-nyu-org/team1-mon-fall26.git
cd team1-mon-fall26
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

### 3. Activate the Virtual Environment

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 5. Apply Database Migrations

```bash
python manage.py migrate
```

### 6. Start the Development Server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser.

To stop the server, press `Ctrl + C` in the terminal.


## Project Structure

```text
team1-mon-fall26/
├── accounts/           # User accounts and authentication
├── bookings/           # Booking requests and management
├── caregivers/         # Caregiver profiles and services
├── config/             # Django project configuration
├── opportunities/      # Public pet-care opportunities
├── pets/               # Pet profiles and information
├── static/             # CSS, JavaScript, and static assets
├── templates/          # Shared HTML templates
├── manage.py           # Django management utility
├── requirements.txt    # Python dependencies
├── .gitignore          # Git exclusion rules
└── README.md           # Project documentation
```

Each Django application is responsible for a specific area of functionality, allowing the team to develop features independently while maintaining a shared project structure.

## Planned Features

PawPal's planned functionality includes:

- **Pet Profiles:** Create and manage profiles containing pet information and care needs.
- **Caregiver Profiles:** Create caregiver profiles and list available services.
- **Caregiver Discovery:** Browse caregivers and view their profiles.
- **Booking Management:** Request, accept, decline, and manage pet-care bookings.
- **Care Opportunities:** Post and browse public pet-care opportunities.
- **Communication:** Support interactions between pet owners and caregivers.
- **Community Features:** Enable reviews and community discussions.
- **Administration:** Support account and content moderation.

Features will be implemented incrementally throughout development.

## UI/UX Design

PawPal's interface and user experience are being designed collaboratively using Figma.

The team will use shared designs and interface references to guide frontend development and maintain consistency across the application.

**Figma Design:** https://www.figma.com/design/b9Ots2MJKqVovgatTdLhjc/PawPal-UI-Design?node-id=5301-28&t=tG12sqdT8IOVGzhz-1

## Development Workflow

The team follows a feature-branch workflow:

- `main` — Stable, approved project code.
- `develop` — Shared integration branch for ongoing development.
- Feature branches — Used for implementing individual features and user stories.

### Contributing Changes

1. Switch to the `develop` branch and pull the latest changes.
2. Create a new feature branch.
3. Implement and test your changes.
4. Commit and push your feature branch.
5. Open a pull request targeting `develop`.
6. Complete the required review process before merging.

Example:

```bash
git switch develop
git pull origin develop
git switch -c feature/example-feature
```

Avoid committing directly to `main`.

## Development Notes

- Use a local virtual environment for Python dependencies.
- Do not commit `.venv/`, local databases, or sensitive configuration files.
- Coordinate changes to shared models and project configuration.
- Keep dependencies documented in `requirements.txt`.
- To add a package, install it and then add one line to `requirements.txt` by hand (for example `whitenoise==6.12.0`). Avoid `pip freeze > requirements.txt` in Windows PowerShell. It saves the file as UTF-16, which GitHub can't display, and it lists every package in your environment.
- When committing, add files by name (`git add path/to/file`) rather than `git add .`, so `db.sqlite3` isn't committed by accident.

## Project Status

PawPal is currently under active development.

The initial project structure and Django applications have been established. Features will be added and integrated through the team's development workflow.
