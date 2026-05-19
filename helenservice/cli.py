from __future__ import annotations

import json
import logging
import os
import sys
from cmd import Cmd
from datetime import date, datetime
from getpass import getpass
from typing import Any, Protocol, overload

from helenservice.api_exceptions import HelenAuthenticationException, InvalidDeliverySiteException

from .api_client import HelenApiClient
from .const import RESOLUTION_HOUR, RESOLUTION_QUARTER
from .price_client import HelenPriceClient
from .utils import get_month_date_range_by_date

logger = logging.getLogger(__name__)


class HasDict(Protocol):
    """Protocol defining objects that possess a __dict__ attribute."""

    __dict__: dict[str, Any]


@overload
def _json_serializer(value: datetime | date) -> str: ...


@overload
def _json_serializer(value: HasDict) -> dict[str, Any]: ...


def _json_serializer(value: datetime | date | HasDict) -> str | dict[str, Any]:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M%S")
    elif isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    else:
        return value.__dict__


def _parse_date_range(input_str: str | None) -> tuple[date, date]:
    """Parse and validate a date range string in format 'YYYY-mm-dd YYYY-mm-dd'.

    Args:
        input_str: Space-separated start and end dates.

    Returns:
        Tuple of (start_date, end_date).

    Raises:
        ValueError: If input is None, empty, malformed, or start_date > end_date.
    """
    if not input_str or not input_str.strip():
        raise ValueError("No date range provided")
    parts = input_str.split()
    if len(parts) != 2:
        raise ValueError("Please provide start and end dates in format 'YYYY-mm-dd YYYY-mm-dd'")
    start_date_str, end_date_str = parts
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    if start_date > end_date:
        raise ValueError("Start date must be before end date")
    return start_date, end_date


class HelenCLIPrompt(Cmd):
    prompt = "helen-cli> "
    intro = "Type ? to list commands"

    def __init__(self, username: str, password: str) -> None:
        super().__init__()
        self._username = username
        self._password = password
        self.helen_price_client = HelenPriceClient()
        self.tax: float = 0.255  # 25.5%
        self.margin: float = self.helen_price_client.get_exchange_prices().margin
        self.api_client = HelenApiClient(self.tax, self.margin)
        self.api_client.login_and_init(username, password)

    def do_exit(self, arg: str | None = None) -> bool:
        """Exit the CLI"""

        self.api_client.close()
        print("Bye")
        return True

    def do_calculate_transfer_fees_between_dates(self, arg: str | None = None) -> None:
        """Calculate the transfer fees between a start date and an end date
        The provided dates should be presented in format 'YYYY-mm-dd'

        Usage example:
        calculate_transfer_fee_between_dates 2022-12-01 2022-12-31
        """

        try:
            start_date, end_date = _parse_date_range(arg)
            price = self.api_client.calculate_transfer_fees_between_dates(start_date, end_date)
            print(price)
        except ValueError:
            print("Please provide proper start and end dates in format 'YYYY-mm-dd'")

    def do_calculate_total_consumption_between_dates(self, arg: str | None = None) -> None:
        """Calculate the total electricity consumption between a start date and an end date
        The provided dates should be presented in format 'YYYY-mm-dd'

        The consumption returned is in kWh.

        Usage example:
        calculate_total_consumption_between_dates 2022-12-01 2022-12-31
        """

        try:
            start_date, end_date = _parse_date_range(arg)
            consumption = self.api_client.get_total_consumption_between_dates(start_date, end_date)
            print(consumption)
        except ValueError:
            print("Please provide proper start and end dates in format 'YYYY-mm-dd'")

    def do_calculate_spot_cost_between_dates(self, arg: str | None = None) -> None:
        """Calculate the price of your Exchange Electricity (spot) contract between a start date and an end date
        The provided dates should be presented in format 'YYYY-mm-dd'

        Includes 10% tax. The price returned is in euros.

        Usage example:
        calculate_spot_cost_between_dates 2022-12-01 2022-12-31
        """

        try:
            start_date, end_date = _parse_date_range(arg)
            price = self.api_client.calculate_total_costs_by_spot_prices_between_dates(start_date, end_date)
            print(price)
        except ValueError:
            print("Please provide proper start and end dates in format 'YYYY-mm-dd'")

    def do_calculate_the_impact_of_usage_between_dates(self, arg: str | None = None) -> None:
        """Calculate the impact of usage for Helen Smart Electricity Guarantee contract
        between a start date and an end date.
        The provided dates should be presented in format 'YYYY-mm-dd'

        Usage example:
        calculate_the_impact_of_usage_between_dates 2022-12-01 2022-12-31
        """

        try:
            start_date, end_date = _parse_date_range(arg)
            impact = self.api_client.calculate_impact_of_usage_between_dates(start_date, end_date)
            print(impact)
        except ValueError:
            print("Please provide proper start and end dates in format 'YYYY-mm-dd'")

    def do_get_monthly_measurements_json(self, arg: str | None = None) -> None:
        """Get the monthly electricity measurements of the on-going year as JSON"""

        year = date.today().year
        monthly_measurements = self.api_client.get_monthly_measurements_by_year(year)
        monthly_measurements_json = json.dumps(monthly_measurements, default=_json_serializer, indent=2)
        print(monthly_measurements_json)

    def do_get_daily_measurements_json(self, arg: str | None = None) -> None:
        """Get the daily electricity measurements of the on-going month of the on-going year as JSON"""

        previous_month_last_day_date, wanted_month_last_day_date = get_month_date_range_by_date(date.today())

        daily_measurements = self.api_client.get_daily_measurements_between_dates(
            previous_month_last_day_date, wanted_month_last_day_date
        )
        daily_measurements_json = json.dumps(daily_measurements, default=_json_serializer, indent=2)
        print(daily_measurements_json)

    def do_get_contract_data_json(self, arg: str | None = None) -> None:
        """Get all your contracts as JSON (includes terminated contracts)"""

        contract_data_json = self.api_client.get_contract_data_json()
        contract_data_json_pretty = json.dumps(contract_data_json, default=_json_serializer, indent=2)
        print(contract_data_json_pretty)

    def do_get_market_prices_json(self, arg: str | None = None) -> None:
        """Get prices for the Market Price contract type as JSON"""

        price = self.helen_price_client.get_market_price_prices()
        price_json = json.dumps(price, default=_json_serializer, indent=2)
        print(price_json)

    def do_get_exchange_margin_price_json(self, arg: str | None = None) -> None:
        """Get margin price for the Exchange Electricity contract type as JSON"""

        price = self.helen_price_client.get_exchange_prices()
        price_json = json.dumps(price, default=_json_serializer, indent=2)
        print(price_json)

    def do_get_contract_base_price(self, arg: str | None = None) -> None:
        """Get the contract base price from your contract data.
        To see the whole contract data as JSON, use get_contract_data_json"""

        base_price = self.api_client.get_contract_base_price()
        print(base_price)

    def do_get_contract_transfer_fee(self, arg: str | None = None) -> None:
        """Get the transfer fee price from your contract data.
        To see the whole contract data as JSON, use get_contract_data_json"""

        base_price = self.api_client.get_transfer_fee()
        print(base_price)

    def do_get_contract_transfer_base_price(self, arg: str | None = None) -> None:
        """Get the transfer base price from your contract data.
        To see the whole contract data as JSON, use get_contract_data_json"""

        base_price = self.api_client.get_transfer_base_price()
        print(base_price)

    def do_get_api_access_token(self, arg: str | None = None) -> None:
        """Get your access token for the Oma Helen API."""

        access_token = self.api_client.get_api_access_token()
        print(access_token)

    def do_refresh_token(self, arg: str | None = None) -> None:
        """Re-authenticate the session. Closes the current session and logs in again.
        Tries to refresh the access token, but if that fails, it will log in again with
        the username and password."""

        self.api_client.close()
        self.api_client.login_and_init(self._username, self._password)
        print(self.api_client.get_api_access_token())

    def do_get_contract_energy_unit_price(self, arg: str | None = None) -> None:
        """Get the energy unit price from your contract data.
        To see the whole contract data as JSON, use get_contract_data_json"""

        contract_energy_unit_price = self.api_client.get_contract_energy_unit_price()
        print(contract_energy_unit_price)

    def do_select_delivery_site(self, arg: str | None = None) -> None:
        """Select a delivery site to be used in the api_client.

        After setting, all measurement requests will be about this delivery site.
        Useful if you have multiple contracts. You may choose your delivery site
        by the GSRN number (18 numbers long) found in your contract or by the
        technical delivery site id (7 numbers long).
        """

        try:
            self.api_client.select_delivery_site_if_valid_id(arg)
        except InvalidDeliverySiteException as e:
            print(e)

    def do_get_all_delivery_sites(self, arg: str | None = None) -> None:
        """Get all delivery site ids across your active contracts."""

        delivery_sites = self.api_client.get_all_delivery_site_ids()
        print(delivery_sites)

    def do_get_all_gsrn_ids(self, arg: str | None = None) -> None:
        """Get all gsrn ids across your active contracts."""

        gsrn_ids = self.api_client.get_all_gsrn_ids()
        print(gsrn_ids)

    def do_get_contract_type(self, arg: str | None = None) -> None:
        """Get the contract type from your contract data.
        To see the whole contract data as JSON, use get_contract_data_json"""

        contract_type = self.api_client.get_contract_type()
        print(contract_type)

    def do_get_spot_prices_chart_data(self, arg: str | None = None) -> None:
        """Get spot prices from chart data API for a single day.
        Data includes 15-minute intervals with VAT and non-VAT prices.
        The provided date should be presented in format 'YYYY-mm-dd'

        Usage example:
        get_spot_prices_chart_data 2025-09-15
        """
        if not arg or not arg.strip():
            print("Please provide a date in format 'YYYY-mm-dd'")
        else:
            try:
                target_date = datetime.strptime(str(arg).strip(), '%Y-%m-%d').date()
                spot_prices = self.api_client.get_spot_prices_from_chart_data(target_date)
                spot_prices_json = json.dumps(spot_prices, default=_json_serializer, indent=2)
                print(spot_prices_json)
            except ValueError:
                print("Please provide a valid date in format 'YYYY-mm-dd'")

    def do_get_hourly_measurements_with_spot_prices_json(self, arg: str | None = None) -> None:
        """Get the measurements with spot prices for each hour between given dates
        The provided dates should be presented in format 'YYYY-mm-dd'

        Usage example:
        get_hourly_measurements_with_spot_prices_json 2025-09-01 2025-09-08
        """
        try:
            start_date, end_date = _parse_date_range(arg)
            measurements_with_spot_prices = self.api_client.get_measurements_with_spot_prices(
                start_date, end_date, RESOLUTION_HOUR
            )
            measurements_json = json.dumps(measurements_with_spot_prices, default=_json_serializer, indent=2)
            print(measurements_json)
        except ValueError:
            print("Please provide proper start and end dates in format 'YYYY-mm-dd'")

    def do_get_quarterly_measurements_with_spot_prices_json(self, arg: str | None = None) -> None:
        """Get the measurements with spot prices for each quarter between given dates
        The provided dates should be presented in format 'YYYY-mm-dd'

        Usage example:
        get_quarterly_measurements_with_spot_prices_json 2025-09-01 2025-09-08
        """
        try:
            start_date, end_date = _parse_date_range(arg)
            measurements_with_spot_prices = self.api_client.get_measurements_with_spot_prices(
                start_date, end_date, RESOLUTION_QUARTER
            )
            measurements_json = json.dumps(measurements_with_spot_prices, default=_json_serializer, indent=2)
            print(measurements_json)
        except ValueError:
            print("Please provide proper start and end dates in format 'YYYY-mm-dd'")


def main() -> None:
    # Configure logging based on environment or flags
    log_level = logging.WARNING
    if "--debug" in sys.argv:
        log_level = logging.DEBUG
        sys.argv.remove("--debug")
    elif "--verbose" in sys.argv:
        log_level = logging.INFO
        sys.argv.remove("--verbose")

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("Log in to Oma Helen")

    # Support credentials via environment variables for automation
    username = os.environ.get("HELEN_USERNAME") or input("Username: ")
    password = os.environ.get("HELEN_PASSWORD") or getpass()

    try:
        HelenCLIPrompt(username, password).cmdloop()
    except HelenAuthenticationException as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
