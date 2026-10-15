
# PawPal 🐾

PawPal is a pet-care platform designed to connect pet owners with caregivers for services such as pet sitting, walking, feeding, and drop-in visits.

The platform will allow pet owners to create pet profiles, discover caregivers, and manage bookings. Caregivers will be able to create professional profiles, offer services, and respond to care requests.

PawPal is being developed collaboratively using Python and Django.

## Local Development Setup

Follow these instructions to set up PawPal on your computer.

### 1. Clone the Repository

```bash
git clone -b develop https://github.com/gcivil-nyu-org/team1-mon-fall26.git
cd team1-mon-fall26
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

This creates an isolated Python environment for the project.

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

This installs the Python packages required to run PawPal.

### 5. Apply Database Migrations

```bash
python manage.py migrate
```

This creates or updates the local database tables.

### 6. Start the Development Server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser to view the application.

To stop the server, press `Ctrl + C` in the terminal.

---

## Project Structure

```text
PawPal/
├── config/              # Shared Django configuration
├── accounts/            # User accounts and authentication
├── pets/                # Pet profiles and care information
├── caregivers/          # Caregiver profiles and discovery
├── opportunities/       # Public pet-care opportunities
├── bookings/            # Booking requests and management
├── templates/           # Shared HTML templates
├── static/              # CSS, JavaScript, and images
├── manage.py            # Django management commands
├── requirements.txt     # Python dependencies
├── .gitignore           # Files excluded from Git
└── README.md            # Project documentation
```

The project is organized into separate Django apps that share the same project configuration and database.

---

## GitHub Development Workflow

Our team uses the following branching structure:

- **main:** Stable, approved code.
- **develop:** Shared development and integration branch.
- **Feature branches:** Individual branches for assigned user stories.

### Working on a Feature

**1. Update your local develop branch:**

```bash
git switch develop
git pull origin develop
```

**2. Create a feature branch:**

```bash
git switch -c feature/your-feature-name
```

**3. Make your changes and commit them:**

```bash
git add .
git commit -m "Describe your changes"
```

**4. Push your feature branch:**

```bash
git push -u origin feature/your-feature-name
```

**5. Open a pull request targeting the `develop` branch.**

Changes should be reviewed and tested before merging.

The `main` branch is reserved for approved code.

---

## Current Sprint Goals

Our initial development sprint focuses on the following functionality:

### Pet Profiles
- Create pet profiles.
- Add basic pet information.
- Save and display pet profiles.

### Caregiver Profiles
- Create caregiver profiles.
- List services offered.
- Save and display caregiver information.

### Caregiver Discovery
- Browse available caregivers.
- View caregiver profiles and services.

### Booking Requests
- Submit a booking request.
- Store booking requests with a Pending status.

### Caregiver Request Management
- View incoming care requests.
- Accept or decline booking requests.
- Update booking statuses.


---

## Team Development Guidelines

- Work on individual feature branches rather than directly on `main`.
- Submit pull requests to `develop` for review.
- Coordinate changes to shared database models and project settings.
- Use sample data where necessary while other features are being developed.
- Test functionality locally before submitting changes.
- Do not commit virtual environments, local databases, or sensitive information.
- Keep the project documentation updated as development progresses.
