.PHONY: build

install:
	python -m pip install -e .
	python -m pip install -r requirements-dev.txt

clean:
	rm -rf dist/ build/

build:
	python -m build
