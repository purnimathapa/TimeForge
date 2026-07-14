# TimeForge

TimeForge is a web-based timetable management system developed as a Semester Project. It helps educational institutions generate, organize, and manage class schedules efficiently while minimizing scheduling conflicts. The system provides an easy-to-use interface for administrators to manage teachers, subjects, rooms, departments, and class routines.

## Project Overview

Creating academic timetables manually is time-consuming and often results in conflicts such as overlapping classes, unavailable teachers, or room allocation issues. TimeForge aims to simplify this process by automating timetable generation while allowing administrators to review and edit schedules before publishing.

## Features

- User Authentication and Authorization
- Dashboard for administrators
- Department Management
- Teacher Management
- Subject Management
- Room Management
- Academic Session and Semester Management
- Automated Timetable Generation
- Conflict Detection and Validation
- Manual Timetable Editing
- Search and Filter Timetables
- Export Timetable as PDF and Excel
- Responsive User Interface

## Technology Stack

### Frontend
- HTML5
- CSS3
- JavaScript
- Bootstrap 5

### Backend
- Python
- Django

### Database
- PostgreSQL

### Development Tools
- Git
- GitHub
- VS Code 
- pgAdmin 4

## Project Structure

```
TimeForge/
│
├── accounts/
├── academics/
├── scheduling/
├── dashboard/
├── core/
├── templates/
├── static/
├── timeforge/
├── manage.py
├── requirements.txt
└── README.md
```

## Installation

### Clone the repository

```bash
git clone https://github.com/yourusername/TimeForge.git

cd TimeForge
```

### Create Virtual Environment

```bash
python3 -m venv venv
```

### Activate Virtual Environment

macOS/Linux

```bash
source venv/bin/activate
```

Windows

```bash
venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure PostgreSQL

Create a PostgreSQL database, then copy `.env.example` to `.env` and set your database credentials (`DB_USER=your_username`, `DB_PASSWORD=your_password`). See `.env.example` for all required environment variables — settings load them via `python-decouple`.

For a full local setup guide, see [docs/SETUP.md](docs/SETUP.md).

### Apply Migrations

```bash
python manage.py makemigrations

python manage.py migrate
```

### Create Superuser

```bash
python manage.py createsuperuser
```

### Run Development Server

```bash
python manage.py runserver
```

Open your browser:

```
http://127.0.0.1:8000/
```

Admin Panel:

```
http://127.0.0.1:8000/admin/
```

## Future Improvements

- AI-assisted timetable optimization
- Email notifications
- Mobile application
- Attendance integration
- Multi-campus support
- Calendar synchronization

## Team Members

- Suyesh Ghimire
- Romin Manandhar
- Pratyush Pokharel
- Rajak Shinkhwal
- Purnima Thapa

## Project Status

This project is being developed as part of the 5th Semester coursework and is currently under active development.

## License

This project is developed for educational purposes only.
