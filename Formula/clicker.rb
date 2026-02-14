class Clicker < Formula
  include Language::Python::Virtualenv

  desc "LLM-powered browser automation agent"
  homepage "https://github.com/spaceorc/clicker"
  head "https://github.com/spaceorc/clicker.git", branch: "master"
  license "MIT"

  depends_on "python@3.13"

  def install
    # Create virtualenv
    virtualenv_create(libexec, "python3.13")

    # Install the package with all dependencies from pyproject.toml
    cd buildpath do
      system libexec/"bin/pip", "install", "--verbose", "."
    end

    # Create wrapper script
    (bin/"clicker").write_env_script libexec/"bin/clicker", PATH: "#{libexec}/bin:$PATH"
  end

  def caveats
    <<~EOS
      After installation, install Playwright browsers:
        #{libexec}/bin/playwright install chromium

      Or use the make command:
        make install  # from clicker source directory
    EOS
  end

  test do
    system "#{bin}/clicker", "--help"
  end
end
