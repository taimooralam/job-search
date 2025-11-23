"""
Convert Markdown CV to Word Document (.docx)

Uses pypandoc with a reference template to preserve professional styling.

Usage:
    python scripts/convert_cv_to_docx.py applications/ASHBY/Staff_Product_Engineer_EU/cv.md
    python scripts/convert_cv_to_docx.py cv.md --output custom_name.docx
    python scripts/convert_cv_to_docx.py cv.md --template assets/custom-template.docx
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default template path
DEFAULT_TEMPLATE = PROJECT_ROOT / "assets" / "template-cv.docx"


def convert_md_to_docx(
    input_path: Path,
    output_path: Path | None = None,
    template_path: Path | None = None
) -> Path:
    """
    Convert a Markdown file to Word document using pypandoc.

    Args:
        input_path: Path to the input .md file
        output_path: Optional output path. Defaults to same directory as input with .docx extension
        template_path: Optional path to reference .docx template for styling

    Returns:
        Path to the generated .docx file

    Raises:
        FileNotFoundError: If input file or template doesn't exist
        RuntimeError: If conversion fails
    """
    try:
        import pypandoc
    except ImportError:
        raise RuntimeError(
            "pypandoc is not installed. Run: pip install pypandoc\n"
            "Also ensure Pandoc is installed: brew install pandoc (macOS) or apt install pandoc (Linux)"
        )

    # Validate input file
    input_path = Path(input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not input_path.suffix == ".md":
        raise ValueError(f"Input file must be a Markdown file (.md): {input_path}")

    # Set default output path
    if output_path is None:
        output_path = input_path.with_suffix(".docx")
    else:
        output_path = Path(output_path).resolve()

    # Set default template path
    if template_path is None:
        template_path = DEFAULT_TEMPLATE
    else:
        template_path = Path(template_path).resolve()

    # Validate template exists
    if not template_path.exists():
        print(f"  Warning: Template not found at {template_path}")
        print(f"  Proceeding without template (basic styling)")
        template_path = None

    # Build extra arguments for pandoc
    extra_args = []
    if template_path:
        extra_args.append(f"--reference-doc={template_path}")

    # Convert using pypandoc
    print(f"  Converting: {input_path.name}")
    print(f"  Template: {template_path.name if template_path else 'None (default styling)'}")

    try:
        pypandoc.convert_file(
            str(input_path),
            'docx',
            outputfile=str(output_path),
            extra_args=extra_args if extra_args else None
        )
    except Exception as e:
        raise RuntimeError(f"Conversion failed: {e}")

    print(f"  Output: {output_path}")
    return output_path


def main():
    """CLI entry point for CV conversion."""
    parser = argparse.ArgumentParser(
        description="Convert Markdown CV to Word document (.docx)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Convert cv.md in an application folder
    python scripts/convert_cv_to_docx.py applications/ASHBY/Staff_Product_Engineer_EU/cv.md

    # Specify custom output name
    python scripts/convert_cv_to_docx.py cv.md --output Taimoor_Alam_CV.docx

    # Use a different template
    python scripts/convert_cv_to_docx.py cv.md --template assets/modern-template.docx

    # Convert all cv.md files in applications folder
    find applications -name "cv.md" -exec python scripts/convert_cv_to_docx.py {} \\;
        """
    )

    parser.add_argument(
        "input",
        type=str,
        help="Path to the input Markdown file (cv.md)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output path for .docx file (default: same location as input)"
    )
    parser.add_argument(
        "--template", "-t",
        type=str,
        default=None,
        help=f"Path to reference .docx template (default: {DEFAULT_TEMPLATE})"
    )

    args = parser.parse_args()

    try:
        print("\n📄 CV Markdown to Word Converter")
        print("=" * 40)

        output_path = convert_md_to_docx(
            input_path=args.input,
            output_path=args.output,
            template_path=args.template
        )

        print("=" * 40)
        print(f"✅ Successfully created: {output_path.name}\n")

    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n❌ Conversion error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
