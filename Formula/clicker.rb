class Clicker < Formula
  include Language::Python::Virtualenv

  desc "LLM-powered browser automation agent"
  homepage "https://github.com/spaceorc/clicker"
  head "https://github.com/spaceorc/clicker.git", branch: "master"
  license "MIT"

  depends_on "python@3.13"

  def install
    # Create virtualenv in libexec
    virtualenv_create(libexec, "python3.13")

    # Install the package and its dependencies
    system libexec/"bin/pip", "install", "-e", buildpath

    # Install Playwright browsers
    system libexec/"bin/playwright", "install", "chromium"

    # Create wrapper script
    (bin/"clicker").write_env_script libexec/"bin/clicker", PATH: "#{libexec}/bin:$PATH"
  end

  test do
    system "#{bin}/clicker", "--help"
  end
end
