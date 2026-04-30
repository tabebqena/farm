#!/bin/bash

# Complete UI Test Runner
# Starts Django server and runs screenshot tests

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if Django server is running
is_server_running() {
    curl -s http://localhost:8000/en/login/ > /dev/null 2>&1
    return $?
}

# Start Django server in background
start_server() {
    print_header "Starting Django Development Server"

    if is_server_running; then
        print_success "Server already running on http://localhost:8000"
        return 0
    fi

    print_info "Starting Django server..."
    python manage.py runserver 0.0.0.0:8000 > django_server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > .django_server.pid

    # Wait for server to start (max 30 seconds)
    for i in {1..30}; do
        if is_server_running; then
            print_success "Django server started (PID: $SERVER_PID)"
            return 0
        fi
        echo -n "."
        sleep 1
    done

    print_error "Server failed to start. Check django_server.log"
    exit 1
}

# Stop Django server if we started it
stop_server() {
    if [ -f ".django_server.pid" ]; then
        PID=$(cat .django_server.pid)
        if kill -0 "$PID" 2>/dev/null; then
            print_info "Stopping Django server (PID: $PID)..."
            kill "$PID" 2>/dev/null || true
            rm -f .django_server.pid
        fi
    fi
}

# Main execution
main() {
    print_header "🏗️  Farm App - Complete UI Test Suite"

    # Cleanup handler
    trap stop_server EXIT

    # Check Python environment
    if ! command -v python &> /dev/null; then
        print_error "Python not found"
        exit 1
    fi

    # Install Playwright if needed
    if ! python -c "import playwright" 2>/dev/null; then
        print_header "Installing Playwright"
        pip install playwright
        playwright install chromium
        print_success "Playwright installed"
    fi

    # Start Django server
    start_server
    print_info "Waiting 2 seconds for server to stabilize..."
    sleep 2

    # Run tests
    print_header "Running UI Tests"
    python test_views_screenshots.py
    TEST_RESULT=$?

    # Generate summary
    print_header "Test Results"
    if [ $TEST_RESULT -eq 0 ]; then
        print_success "All tests passed!"
    else
        print_info "Some tests failed - check report for details"
    fi

    # Open report
    REPORT_PATH="test_screenshots/report.html"
    if [ -f "$REPORT_PATH" ]; then
        print_success "Report generated: $REPORT_PATH"
        print_info "Opening report in browser..."

        if command -v xdg-open &> /dev/null; then
            xdg-open "$REPORT_PATH"
        elif command -v open &> /dev/null; then
            open "$REPORT_PATH"
        else
            echo "Open this file in your browser: file://$(pwd)/$REPORT_PATH"
        fi
    fi

    print_header "Test Suite Complete"
    exit $TEST_RESULT
}

main
