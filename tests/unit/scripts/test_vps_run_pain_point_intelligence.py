from scripts.vps_run_pain_point_intelligence import parse_args


def test_parse_args_defaults_stage_name_to_pain_point_intelligence():
    args = parse_args(["--job-id", "6925a6c845fa3c355f83f8ec"])

    assert args.mode == "stage"
    assert args.stage_name == "pain_point_intelligence"


def test_parse_args_accepts_single_stage_override():
    args = parse_args(
        [
            "--job-id",
            "6925a6c845fa3c355f83f8ec",
            "--mode",
            "stage",
            "--stage-name",
            "stakeholder_surface",
        ]
    )

    assert args.mode == "stage"
    assert args.stage_name == "stakeholder_surface"
