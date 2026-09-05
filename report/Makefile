# Builds report/build/main.pdf (Tectonic) and, if pandoc is installed, a Word version
# for departments that require .docx.
.PHONY: all pdf docx clean

all: pdf

pdf:
	mkdir -p build
	tectonic -X compile main.tex --outdir build

docx:
	@command -v pandoc >/dev/null || { echo "pandoc not installed (brew install pandoc)"; exit 1; }
	mkdir -p build
	pandoc main.tex --citeproc --bibliography=../paper/references.bib -o build/report.docx

clean:
	rm -rf build
