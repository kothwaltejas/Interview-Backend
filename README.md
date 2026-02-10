# Intervu AI Backend

AI-powered backend services for resume parsing and interview preparation using FastAPI and LLaMA via GROQ.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ 
- GROQ API Key (get from [GROQ Console](https://console.groq.com/))

### Setup

1. **Clone and navigate to backend:**
   ```bash
   cd backend
   ```

2. **Copy environment file:**
   ```bash
   # Windows
   copy .env.example .env
   
   # Linux/Mac
   cp .env.example .env
   ```

3. **Configure your API keys in `.env`:**
   ```env
   GROQ_API_KEY=your_actual_groq_api_key_here
   ```

4. **Start the server:**
   
   **Windows:**
   ```bash
   start.bat
   ```
   
   **Linux/Mac:**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

   **Manual setup:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cd src
   python main.py
   ```

## 📋 API Endpoints

### Health Check
```http
GET /
GET /health
```

### Resume Parser
```http
POST /api/resume/parse
Content-Type: multipart/form-data

Body:
- file: PDF file (max 10MB)
```

**Response:**
```json
{
  "success": true,
  "data": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "education": [
      {
        "degree": "Bachelor of Science in Computer Science",
        "institution": "University of Technology", 
        "year": "2020"
      }
    ],
    "skills": ["Python", "JavaScript", "React", "FastAPI"],
    "experience": [
      {
        "title": "Software Developer",
        "company": "Tech Corp",
        "duration": "2020-2023", 
        "description": "Built web applications..."
      }
    ],
    "projects": [
      {
        "title": "E-commerce Platform",
        "tech": ["React", "Node.js", "MongoDB"],
        "description": "Full-stack e-commerce solution..."
      }
    ]
  },
  "filename": "resume.pdf"
}
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | GROQ API key for LLaMA access | Required |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:5173,http://localhost:3000` |
| `LOG_LEVEL` | Logging level | `INFO` |

## 🏗️ Architecture

```
backend/
├── src/
│   ├── main.py                 # FastAPI application
│   └── services/
│       ├── __init__.py
│       ├── llm_groq_config.py  # LLM configuration
│       └── resume_parser.py    # Resume parsing logic
├── requirements.txt            # Python dependencies
├── start.bat                   # Windows startup script
├── start.sh                    # Linux/Mac startup script
└── .env.example               # Environment template
```

## Project Structure
```
src/
├── config/       # Configuration files (database, environment)
├── routes/       # API route definitions
├── controllers/  # Request handlers and business logic
├── services/     # Core business logic and AI integration
├── models/       # Data models and schemas
├── middlewares/  # Custom middleware (auth, validation, etc.)
├── utils/        # Helper functions and utilities
└── app.js        # Express application setup

tests/            # Unit and integration tests
```

## Getting Started

### Prerequisites
- Node.js (v16 or higher)
- npm or yarn

### Installation
```bash
npm install
```

### Configuration
1. Copy `.env.example` to `.env`
2. Update the environment variables with your configuration

### Development
```bash
npm run dev
```

### Production
```bash
npm start
```

## API Endpoints (To be implemented)
- `/api/auth` - Authentication endpoints
- `/api/interviews` - Interview management
- `/api/analysis` - AI analysis and feedback
- `/api/users` - User management

## Features (To be implemented)
- RESTful API design
- JWT-based authentication
- AI-powered interview analysis
- Real-time communication (WebSocket/Socket.io)
- Database integration
- Python script integration for ML models
