ci-prime:
    act -j unit --pull -e event.json -W .github/workflows

ci-unit:
    act -j unit --pull=false -e event.json -W .github/workflows

ci: ci-unit

pre-commit:
    just ci-unit

pre-push:
    just test-unit
    just ci-unit
