# so101-lab — ドキュメント配信など
# Docs: uv sync --group docs && make docs-serve
# Sim:  make sim-kamino   (Newton/Kamino GPU sim — docs/22_kamino_sim.md)

.PHONY: help docs-serve docs-build docs-print docs-sync sim-sync sim-kamino mlflow-serve mlflow-stop mlflow-logs publish-public

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk -F ':.*?## ' '{printf "  %-16s %s\n", $$1, $$2}'

docs-sync: ## Install MkDocs deps (uv group docs)
	uv sync --group docs

docs-serve: docs-sync ## Serve docs on LAN (http://<PC-IP>:8100)
	uv run mkdocs serve --dev-addr 0.0.0.0:8100

docs-build: docs-sync ## Build static site into site/
	uv run mkdocs build

docs-print: docs-sync ## Single-file offline HTML of ALL docs -> print/so101-lab_docs.html
	uv run mkdocs build
	@mkdir -p print
	uv run python scripts/inline_print_page.py site/print_page/index.html print/so101-lab_docs.html

sim-sync: ## Install Newton (Kamino) GPU sim deps (uv group sim)
	uv sync --group sim

sim-kamino: sim-sync ## SO-101 Kamino smoke test on GPU (docs/22_kamino_sim.md)
	uv run --group sim python scripts/kamino_check.py

mlflow-serve: ## Local MLflow UI via Docker (:5000, store is gitignored)
	./scripts/start_mlflow.sh

mlflow-stop: ## Stop Docker MLflow container
	docker compose stop mlflow

mlflow-logs: ## Tail Docker MLflow logs
	docker compose logs -f mlflow

# 提出用スナップショット: tracked ファイルのみ（= 個人設定は含まれない）を
# 別の public リポジトリへ書き出す。使い方:
#   make publish-public DIR=~/robot/so101-lab-public
# 初回は DIR 側で git init + remote 追加しておく。以後はコミットを積んで push。
publish-public: ## Export tracked files only -> DIR (submission snapshot)
ifndef DIR
	$(error DIR=<export-dir> is required. e.g. make publish-public DIR=$$HOME/robot/so101-lab-public)
endif
	@test -d "$(DIR)" || { echo "ERROR: $(DIR) does not exist (git init しておくこと)"; exit 1; }
	git archive HEAD | tar -x -C "$(DIR)"
	@git ls-files | while IFS= read -r f; do \
		if [ ! -e "$(DIR)/$$f" ]; then \
			mkdir -p "$(DIR)/$$(dirname "$$f")"; \
			git show "HEAD:$$f" > "$(DIR)/$$f"; \
			echo "restored (archive skipped): $$f"; \
		fi; \
	done
	@echo "Exported tracked files to $(DIR)."
	@echo "Next: cd $(DIR) && git add -A && git commit -m 'Snapshot $$(date +%Y-%m-%d)' && git push"
